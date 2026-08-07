import os
import requests
import json

base_url = os.getenv('QDRANT_URL', 'http://127.0.0.1:6333')
collection_name = 'knowledge_segment'

print('=' * 60)
print(f'Testing Collection: {collection_name}')
print('=' * 60)
print()

# 1. 获取集合详情
print('[1] Collection Details:')
resp = requests.get(f'{base_url}/collections/{collection_name}')
info = resp.json()['result']
config = info['config']
params = config['params']
vectors = params['vectors']

print(f'  Vector size: {vectors["size"]}')
print(f'  Distance: {vectors["distance"]}')
print(f'  Points count: {info["points_count"]}')
print(f'  Indexed: {info["indexed_vectors_count"]}')
print()

# 2. Scroll 查看数据结构
print('[2] Sample Data (first 5 points):')
scroll_resp = requests.post(
    f'{base_url}/collections/{collection_name}/points/scroll',
    json={
        'limit': 5,
        'with_payload': True,
        'with_vector': False
    }
)
scroll_result = scroll_resp.json()['result']
points = scroll_result['points']

for i, p in enumerate(points):
    print(f'  --- Point {i+1} (ID: {p["id"]}) ---')
    payload = p.get('payload', {})
    for key, value in payload.items():
        # 截断长文本
        str_value = str(value)
        if len(str_value) > 100:
            str_value = str_value[:100] + '...'
        print(f'    {key}: {str_value}')
    print()

# 3. 查看 payload 中的所有字段
print('[3] All Payload Fields:')
all_fields = set()
for p in points:
    all_fields.update(p.get('payload', {}).keys())
print(f'  Fields: {", ".join(sorted(all_fields))}')
print()

# 4. 搜索能耗相关数据
print('[4] Search for energy consumption data:')
print('  Searching with keywords...')
print()

# 由于没有嵌入模型，我们用 scroll + filter 方式查找
# 先看看有没有 energy/能耗 相关的字段值
print('[5] Scanning all points for energy-related content...')

all_points = []
next_offset = None
while True:
    scroll_body = {
        'limit': 100,
        'with_payload': True,
        'with_vector': False
    }
    if next_offset:
        scroll_body['offset'] = next_offset

    scroll_resp = requests.post(
        f'{base_url}/collections/{collection_name}/points/scroll',
        json=scroll_body
    )
    result = scroll_resp.json()['result']
    batch = result.get('points', [])
    all_points.extend(batch)

    next_offset = result.get('next_page_offset')
    if not next_offset or not batch:
        break

print(f'  Total points loaded: {len(all_points)}')
print()

# 搜索包含"能耗"、"energy"、"consumption"等关键词的数据
energy_keywords = ['能耗', 'energy', 'consumption', '电力', '电量', '功率', 'power', '节能', 'kwh', '千瓦', '用电']
energy_points = []

for p in all_points:
    payload = p.get('payload', {})
    payload_str = json.dumps(payload, ensure_ascii=False).lower()
    for keyword in energy_keywords:
        if keyword.lower() in payload_str:
            energy_points.append((p, keyword))
            break

print(f'[6] Energy-related points found: {len(energy_points)}')
print()

if energy_points:
    print('[7] Energy Data Details:')
    for i, (p, keyword) in enumerate(energy_points[:10]):  # 显示前10条
        print(f'  --- Match {i+1} (ID: {p["id"]}, keyword: {keyword}) ---')
        payload = p.get('payload', {})
        for key, value in payload.items():
            str_value = str(value)
            if len(str_value) > 150:
                str_value = str_value[:150] + '...'
            print(f'    {key}: {str_value}')
        print()
else:
    print('  No energy-related data found with keyword search.')
    print()

# 8. 查看所有数据的分类/类型分布
print('[8] Data Distribution Analysis:')
category_fields = ['category', 'type', 'source', 'tag', 'label']
for field in category_fields:
    values = {}
    for p in all_points:
        val = p.get('payload', {}).get(field)
        if val:
            values[val] = values.get(val, 0) + 1
    if values:
        print(f'  {field} distribution:')
        for val, count in sorted(values.items(), key=lambda x: -x[1])[:10]:
            print(f'    {val}: {count}')
        print()

# 9. 显示第一条完整数据结构
print('[9] Full payload structure of first point:')
if all_points:
    first = all_points[0]
    print(json.dumps(first.get('payload', {}), indent=2, ensure_ascii=False))

print()
print('=' * 60)
print('Test completed!')
print('=' * 60)
