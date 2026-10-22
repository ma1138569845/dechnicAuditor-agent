"""设备/场景采集：格式化、合并、变配电关联和场景映射。"""

from dataclasses import asdict
from unittest.mock import MagicMock

from tools.energy_audit import pg_collector as pgc
from tools.energy_audit.pg_query import PgDataQuery
from tools.energy_audit.project_data import Equipment, shared_office_metering_sentence
from tools.energy_audit_tool import _format_equipment_section, _format_project_summary


def test_fmt_device_keeps_independent_metering_yes():
    rec = {
        'device_name': 'LED灯',
        'device_num': 12,
        'brand_model': 'PHILIPS',
        'is_metering': 1,
        'metering_desc': '楼层电表',
        'metering_ratio': '80%',
        'metering_time': '2024-01-01~2025-01-01',
    }
    out = PgDataQuery._fmt_device(rec, '照明')
    assert out['name'] == 'LED灯'
    assert out['quantity'] == 12
    assert out['independent_metering'] == '有'
    assert out['independent_metering_desc'] == '楼层电表'
    assert out['independent_metering_ratio'] == '80%'
    assert out['independent_metering_time'] == '2024-01-01~2025-01-01'


def test_fmt_device_keeps_independent_metering_no():
    out = PgDataQuery._fmt_device(
        {'device_name': '螺杆机', 'device_num': 2, 'is_metering': 0},
        '空调',
    )
    assert out['independent_metering'] == '无'


def test_fmt_device_without_column_leaves_metering_blank():
    out = PgDataQuery._fmt_device({'device_name': '电脑', 'device_num': 3}, '办公')
    assert out['independent_metering'] == ''
    assert out['independent_metering_desc'] == ''


def test_merge_equipment_keeps_all_devices_and_metering():
    pg = [
        {'name': 'LED灯', 'category': '照明', 'spec': '18W', 'quantity': 10,
         'independent_metering': '有'},
        {'name': 'T8灯管', 'category': '照明', 'spec': '36W', 'quantity': 8,
         'independent_metering': '无'},
    ]
    merged = pgc._merge_equipment(pg, [])
    assert len(merged) == 2
    assert [e.name for e in merged] == ['LED灯', 'T8灯管']
    assert merged[0].independent_metering == '有'
    assert merged[1].independent_metering == '无'


def test_merge_equipment_ignores_unknown_keys():
    merged = pgc._merge_equipment([
        {'name': '锅炉', 'category': '蒸汽', 'spec': '', 'quantity': 1,
         'independent_metering': '有', 'extra_pg_col': 1},
    ])
    assert isinstance(merged[0], Equipment)
    assert merged[0].independent_metering == '有'


def test_get_all_devices_queries_td_table():
    q = PgDataQuery.__new__(PgDataQuery)
    q.version_code = None
    called = []

    def fake(table, customer_id=None):
        called.append(table)
        return []

    q._get_device_by_table = fake
    q.get_device_substation = lambda customer_id=None: []
    cats = q.get_all_devices(customer_id=9)
    assert 'ts_institution_device_td' in called
    assert 'ts_institution_device_light' in called
    assert '输配设备' in cats


def _substation_query(version_code=None):
    q = PgDataQuery.__new__(PgDataQuery)
    q.version_code = PgDataQuery.normalize_version_code(version_code)
    q.connection = None
    captured = []
    main_rows = [
        {
            'id': 2, 'customer_id': 9, 'electricity_name': '中心配电室',
            'brand_model': '', 'is_draft': 1, 'version_code': None,
            'supply_area': '医院所有区域', 'load_rate': '65%',
        },
        {
            'id': 3, 'customer_id': 9, 'electricity_name': '中心配电室',
            'brand_model': '', 'is_draft': 0, 'version_code': 'PL2026090211',
            'supply_area': '正式版本', 'load_rate': '50%',
        },
        {
            'id': 1, 'customer_id': 9, 'electricity_name': '1号配电室',
            'brand_model': '', 'is_draft': 0, 'version_code': 'PL2026090201',
            'supply_area': '旧范围', 'load_rate': '40%',
        },
        {
            'id': 4, 'customer_id': 9, 'electricity_name': '1号配电室',
            'brand_model': '', 'is_draft': 0, 'version_code': 'PL2026090201',
            'supply_area': '全院', 'load_rate': '45%',
        },
    ]
    attachment_rows = [
        {
            'id': 20, 'device_id': 2, 'customer_id': None,
            'device_name': '变压器1', 'device_num': 4, 'capacity': 1000,
            'type': '干式变压器', 'device_model': 'SUB11-1000/10',
            'deleted': 0, 'is_draft': 1, 'version_code': None,
        },
        {
            'id': 21, 'device_id': 2, 'customer_id': None,
            'device_name': '2号变压器', 'device_num': 2, 'capacity': 800,
            'type': '干式变压器', 'device_model': 'SUB11-800/10',
            'deleted': 0, 'is_draft': 1, 'version_code': None,
        },
        {
            'id': 22, 'device_id': 2, 'customer_id': None,
            'device_name': '2号变压器', 'device_num': 2, 'capacity': 630,
            'type': '干式变压器', 'device_model': 'SUB11-630/10',
            'deleted': 0, 'is_draft': 1, 'version_code': None,
        },
        {
            'id': 23, 'device_id': 2, 'customer_id': None,
            'device_name': '已删除变压器', 'device_num': 1, 'capacity': 500,
            'type': '干式变压器', 'device_model': 'DELETED',
            'deleted': 1, 'is_draft': 1, 'version_code': None,
        },
        {
            'id': 24, 'device_id': 4, 'customer_id': None,
            'device_name': '1号变压器', 'device_num': 4, 'capacity': 1000,
            'type': '干式变压器', 'device_model': 'SUB11-1000/10',
            'deleted': 0, 'is_draft': 0, 'version_code': 'PL2026090211',
        },
    ]

    def fake_execute(sql, params=None):
        captured.append((sql, params))
        if 'ts_institution_device_attached' in sql:
            return attachment_rows
        if 'ts_institution_device_substation' in sql:
            return main_rows
        return []

    q._execute = fake_execute
    return q, captured


def test_substation_current_draft_supersedes_unversioned_legacy_and_links_attachments():
    q, _ = _substation_query()
    rooms = q.get_device_substation(customer_id=9)

    assert [r['electricity_name'] for r in rooms] == ['中心配电室']
    center = rooms[0]

    assert center['id'] == 2
    assert center['supply_area'] == '医院所有区域'
    assert [a['capacity'] for a in center['attachments']] == [1000, 800, 630]


def test_substation_version_lock_excludes_drafts_and_uses_selected_ids_for_attachments():
    q, captured = _substation_query(version_code='PL2026090211')
    q.get_device_substation(customer_id=9)

    assert len(captured) == 2
    assert 't.version_code = %s' in captured[0][0]
    assert captured[0][1][-1] == 'PL2026090211'
    # 附属表实测无 version_code/is_draft；版本定位只发生在主表，
    # 附属表以已选主表 id 作为唯一归属边界。
    assert 'a.version_code' not in captured[1][0]
    assert captured[1][1] == (tuple([3]),)


def test_get_all_devices_includes_substation_category():
    q = PgDataQuery.__new__(PgDataQuery)
    q.version_code = None
    q._get_device_by_table = lambda table, customer_id=None: []
    q.get_device_substation = lambda customer_id=None: [{
        'id': 2, 'electricity_name': '中心配电室', 'attachments': [],
    }]

    cats = q.get_all_devices(customer_id=9)
    assert cats['变配电'][0]['electricity_name'] == '中心配电室'


def test_formatted_substation_keeps_transformer_attachments():
    out = PgDataQuery._fmt_device({
        'id': 2,
        'electricity_name': '中心配电室',
        'electricity_area': '医院所有区域',
        'electricity_crossing': '无',
        'other_electricity': 0,
        'load_rate': '65.00',
        'remain_capacity': '1000.00',
        'attachments': [
            {
                'device_name': '变压器1', 'device_num': 4, 'capacity': 1000,
                'type': '干式变压器', 'device_model': 'SUB11-1000/10',
            },
            {
                'device_name': '2号变压器', 'device_num': 2, 'capacity': 800,
                'type': '干式变压器', 'device_model': 'SUB11-800/10',
            },
        ],
    }, '变配电')

    assert out['name'] == '中心配电室'
    assert out['category'] == '变配电'
    assert out['quantity'] == 6
    assert out['substation_id'] == 2
    assert out['supply_area'] == '医院所有区域'
    assert out['out_supply'] == '否'
    assert out['remaining_capacity'] == '1000.00'
    assert '日常负载率:65%' in out['spec']
    assert len(out['attachments']) == 2


def test_equipment_dataclass_persists_substation_attachments():
    equipment = pgc._dataclass_from_dict(Equipment, {
        'name': '中心配电室',
        'category': '变配电',
        'quantity': 6,
        'substation_id': 2,
        'attachments': [{
            'device_name': '变压器1',
            'device_num': 4,
            'capacity': 1000,
        }],
    })

    assert asdict(equipment)['attachments'][0]['capacity'] == 1000


def test_collect_scene_independent_metering_flags():
    pg = MagicMock()
    pg.find_project_by_name.return_value = {
        'id': 1, 'customer_id': 9, 'audited_name': '测试单位',
        'audit_dept_name': '审计机构',
    }
    pg.get_customer_info.return_value = []
    pg.get_institution_build.return_value = []
    pg.get_institution_energy.return_value = []
    pg.get_formatted_equipment.return_value = []
    pg.get_project_audit_users.return_value = []
    pg.get_project_audited_users.return_value = []
    pg.get_energy_meter.return_value = []
    pg.get_energy_standards.return_value = []
    pg.get_institution_energy_saving.return_value = []
    pg.get_institution_scene.return_value = [{
        'id': 88,
        'energy_metering': 1,
        'separate_meter': 1,
        'mode': 2,
        'split_measure': 1,
        'split_payment': 2,
        'light_socket_meter': 1,
        'power_meter': 0,
        'aircon_meter': 1,
        'special_meter': 0,
        'other_special_meter': '机房单独计量',
        'construction_elec_meter': 0,
        'construction_water_meter': 1,
    }]
    pg.get_institution_scene_mode.return_value = []

    found = pgc._collect_from_pg_impl(pg, '测试单位')['found']['metering']
    assert found['has_separate_metering'] is True
    assert found['has_household_metering'] is True
    assert found['has_household_payment'] is False
    assert found['has_shared_office'] is False
    assert found['independent_light_socket'] is True
    assert found['independent_power'] is False
    assert found['independent_aircon'] is True
    assert found['independent_special'] is False
    assert found['independent_other_special'] == '机房单独计量'
    assert found['independent_construction_elec'] is False
    assert found['independent_construction_water'] is True


def test_equipment_section_shows_independent_metering():
    md = _format_equipment_section([
        {'name': 'LED灯', 'category': '照明', 'spec': '18W', 'quantity': 10,
         'independent_metering': '有', 'independent_metering_desc': '楼层电表'},
    ])
    assert '独立计量：有' in md
    assert '楼层电表' in md


def test_project_summary_shows_scene_independent_meters():
    md = _format_project_summary({
        'found': {
            'metering': {
                'has_monitoring_system': True,
                'has_separate_metering': True,
                'has_household_metering': False,
                'independent_light_socket': True,
                'independent_power': False,
                'independent_aircon': True,
                'independent_special': False,
                'independent_other_special': '机房',
                'independent_construction_elec': False,
                'independent_construction_water': False,
            }
        },
        'missing': [],
    })
    assert '照明插座独立计量：是' in md
    assert '动力用电独立计量：否' in md
    assert '机房' in md


def _pg_for_scene(scene, modes=None):
    pg = MagicMock()
    pg.find_project_by_name.return_value = {
        'id': 1, 'customer_id': 9, 'audited_name': '测试单位',
        'audit_dept_name': '审计机构',
    }
    pg.get_customer_info.return_value = []
    pg.get_institution_build.return_value = []
    pg.get_institution_energy.return_value = []
    pg.get_formatted_equipment.return_value = []
    pg.get_project_audit_users.return_value = []
    pg.get_project_audited_users.return_value = []
    pg.get_energy_meter.return_value = []
    pg.get_energy_standards.return_value = []
    pg.get_institution_energy_saving.return_value = []
    pg.get_institution_scene.return_value = scene
    pg.get_institution_scene_mode.return_value = modes or []
    return pg


def test_mode_is_shared_office_not_household_metering():
    """scene.mode 是合署办公；分户计量走 split_measure。"""
    pg = _pg_for_scene([{
        'id': 10, 'mode': 1, 'split_measure': 2, 'split_payment': 1,
        'energy_metering': 2, 'separate_meter': 2,
    }])
    found = pgc._collect_from_pg_impl(pg, '测试单位')['found']
    metering = found['metering']
    assert metering['has_shared_office'] is True
    assert metering['has_household_metering'] is False
    assert metering['has_household_payment'] is True
    pg.get_institution_scene_mode.assert_called_once()
    kwargs = pg.get_institution_scene_mode.call_args.kwargs
    assert kwargs.get('customer_id') == 9
    assert kwargs.get('scene_id') == 10


def test_collects_scene_mode_independent_metering():
    pg = _pg_for_scene(
        [{'id': 10, 'mode': 1, 'split_measure': 1, 'split_payment': 1}],
        [{
            'mode_dept_name': '县档案馆',
            'mode_reason': '同楼办公',
            'pay_type': '电费分摊',
            'start_time': '2023-01-01',
            'end_time': '2025-12-31',
            'mode_build': '南楼3层',
            'mode_area': 320.5,
            'mode_ratio': 15.0,
            'is_metering': 0,
        }],
    )
    found = pgc._collect_from_pg_impl(pg, '测试单位')['found']
    assert found['metering']['has_shared_office'] is True
    rows = found['shared_offices']
    assert len(rows) == 1
    assert rows[0]['dept_name'] == '县档案馆'
    assert rows[0]['building'] == '南楼3层'
    assert rows[0]['independent_metering'] == '无'
    assert rows[0]['pay_type'] == '电费分摊'


def test_project_summary_shows_shared_office_metering():
    md = _format_project_summary({
        'found': {
            'metering': {
                'has_shared_office': True,
                'has_household_metering': True,
                'has_monitoring_system': False,
                'has_separate_metering': False,
            },
            'shared_offices': [
                {'dept_name': '县档案馆', 'building': '南楼3层',
                 'independent_metering': '无', 'area': 320},
            ],
        },
        'missing': [],
    })
    assert '有合署办公，但未实现各办公单位独立计量' in md
    assert '合署办公：是' not in md
    assert '合署办公：否' not in md
    assert '县档案馆' in md
    assert '独立计量：无' in md


def test_shared_office_metering_sentence_rules():
    assert shared_office_metering_sentence(False, []) == ""
    assert shared_office_metering_sentence(False, [
        {'independent_metering': '无'},
    ]) == ""
    assert shared_office_metering_sentence(True, []) == "有合署办公，但未实现各办公单位独立计量"
    assert shared_office_metering_sentence(True, [
        {'independent_metering': '无'},
        {'independent_metering': '有'},
    ]) == "有合署办公且实现了合办公单位独立计量"
    assert shared_office_metering_sentence(True, [
        {'independent_metering': '无'},
        {'independent_metering': '否'},
    ]) == "有合署办公，但未实现各办公单位独立计量"

