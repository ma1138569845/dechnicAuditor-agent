import os
import requests
import json
import random

base_url = os.getenv('QDRANT_URL', 'http://127.0.0.1:6333')

print('=' * 50)
print('Qdrant Full Function Test')
print('=' * 50)
print()

# 1. 创建测试集合
print('[1] Creating test collection...')
test_collection = 'test_collection'

# 删除已存在的测试集合（如果有）
requests.delete(f'{base_url}/collections/{test_collection}')

create_resp = requests.put(
    f'{base_url}/collections/{test_collection}',
    json={
        'vectors': {
            'size': 128,
            'distance': 'Cosine'
        }
    }
)
print(f'  Create result: {create_resp.json()["status"]}')
print()

# 2. 插入测试数据
print('[2] Inserting test points...')

points = []
categories = ['technology', 'science', 'history', 'art']
for i in range(10):
    points.append({
        'id': i + 1,
        'vector': [random.random() for _ in range(128)],
        'payload': {
            'category': categories[i % 4],
            'title': f'Test Document {i+1}',
            'score': random.randint(60, 100)
        }
    })

upsert_resp = requests.put(
    f'{base_url}/collections/{test_collection}/points',
    json={'points': points}
)
print(f'  Insert result: {upsert_resp.json()["status"]}')
print(f'  Points inserted: {len(points)}')
print()

# 3. 获取集合信息
print('[3] Collection info after insert...')
info_resp = requests.get(f'{base_url}/collections/{test_collection}')
info = info_resp.json()['result']
print(f'  Points count: {info["points_count"]}')
print()

# 4. 搜索测试（无过滤）
print('[4] Search test (no filter)...')
query_vector = [random.random() for _ in range(128)]

search_resp = requests.post(
    f'{base_url}/collections/{test_collection}/points/search',
    json={
        'vector': query_vector,
        'limit': 3,
        'with_payload': True
    }
)
results = search_resp.json()['result']
print(f'  Found {len(results)} results:')
for r in results:
    print(f'    ID: {r["id"]}, Score: {r["score"]:.4f}, Title: {r["payload"]["title"]}')
print()

# 5. 带过滤条件的搜索
print('[5] Search with filter (category=science)...')

filtered_resp = requests.post(
    f'{base_url}/collections/{test_collection}/points/search',
    json={
        'vector': query_vector,
        'limit': 3,
        'with_payload': True,
        'filter': {
            'must': [
                {
                    'key': 'category',
                    'match': {'value': 'science'}
                }
            ]
        }
    }
)
filtered_results = filtered_resp.json()['result']
print(f'  Found {len(filtered_results)} results:')
for r in filtered_results:
    print(f'    ID: {r["id"]}, Score: {r["score"]:.4f}, Category: {r["payload"]["category"]}')
print()

# 6. 范围过滤测试
print('[6] Range filter test (score >= 85)...')

range_resp = requests.post(
    f'{base_url}/collections/{test_collection}/points/search',
    json={
        'vector': query_vector,
        'limit': 5,
        'with_payload': True,
        'filter': {
            'must': [
                {
                    'key': 'score',
                    'range': {'gte': 85}
                }
            ]
        }
    }
)
range_results = range_resp.json()['result']
print(f'  Found {len(range_results)} results:')
for r in range_results:
    print(f'    ID: {r["id"]}, Score: {r["payload"]["score"]}, Title: {r["payload"]["title"]}')
print()

# 7. 获取单个点
print('[7] Get single point by ID...')
get_resp = requests.get(f'{base_url}/collections/{test_collection}/points/1')
point = get_resp.json()['result']
print(f'  Point ID: {point["id"]}')
print(f'  Payload: {json.dumps(point["payload"], indent=4)}')
print()

# 8. 更新 payload
print('[8] Update point payload...')
update_resp = requests.post(
    f'{base_url}/collections/{test_collection}/points/payload',
    json={
        'points': [1],
        'payload': {
            'updated': True,
            'note': 'This point was updated'
        }
    }
)
print(f'  Update result: {update_resp.json()["status"]}')

# 验证更新
verify_resp = requests.get(f'{base_url}/collections/{test_collection}/points/1')
updated_point = verify_resp.json()['result']
print(f'  Updated payload: {json.dumps(updated_point["payload"], indent=4)}')
print()

# 9. 删除测试点
print('[9] Delete test points (ID 9, 10)...')
delete_resp = requests.post(
    f'{base_url}/collections/{test_collection}/points/delete',
    json={
        'points': [9, 10]
    }
)
print(f'  Delete result: {delete_resp.json()["status"]}')

# 验证删除
info_after_delete = requests.get(f'{base_url}/collections/{test_collection}')
print(f'  Points count after delete: {info_after_delete.json()["result"]["points_count"]}')
print()

# 10. Scroll 遍历测试
print('[10] Scroll through points...')
scroll_resp = requests.post(
    f'{base_url}/collections/{test_collection}/points/scroll',
    json={
        'limit': 5,
        'with_payload': True
    }
)
scroll_result = scroll_resp.json()['result']
print(f'  Points in first page: {len(scroll_result["points"])}')
for p in scroll_result['points']:
    print(f'    ID: {p["id"]}, Title: {p["payload"]["title"]}')
print()

# 11. 清理测试集合
print('[11] Cleanup - deleting test collection...')
delete_collection_resp = requests.delete(f'{base_url}/collections/{test_collection}')
print(f'  Delete collection result: {delete_collection_resp.json()["status"]}')
print()

print('=' * 50)
print('All tests completed successfully!')
print('=' * 50)