# -*- coding: utf-8 -*-
"""导入反编译的运维检查项目录到知识图谱

从外部反编译产物目录读取检查项目录（JSON），批量建 check_item 实体，
并建立 applies_to（→数据库产品）与 diagnoses（→错误码）关系。

用法:
    python tools/import_check_items.py --dir <json目录> [--dry-run]
    # 目录也可用环境变量 CHECK_ITEMS_JSON_DIR 提供
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# db_type → 知识图谱 database_product 的 normalized_name 映射
DB_TYPE_PRODUCT = {
    'oracle': 'oracle', 'mysql': 'mysql', 'postgresql': 'postgresql',
    'sqlserver': 'sqlserver', 'dm': 'dameng', 'gaussdb': 'gaussdb',
    'oceanbase': 'oceanbase', 'mongodb': 'mongodb', 'goldendb': 'goldendb',
    'tdsql': 'tdsql', 'db2': 'db2',
}

_ORA_CODE_RE = re.compile(r'ORA-\d{4,5}', re.IGNORECASE)
_ERR_CODE_RE = re.compile(r'\bERROR\s+\d+\b', re.IGNORECASE)


def extract_error_codes(item):
    """从脚本名与知识文案提取错误码归一化名集合

    ORA-00600 → 'ora-00600'；ERROR 1045 → 'error 1045'（与图谱 error_code 命名一致）
    """
    codes = set()
    text = (item.get('name', '') + ' '
            + ' '.join(item.get('knowledge_text', []))
            + ' ' + ' '.join(item.get('sql', [])))
    for m in _ORA_CODE_RE.findall(text):
        codes.add('ora-' + m.upper().split('-')[1].lower())
    for m in _ERR_CODE_RE.findall(text):
        codes.add('error ' + m.split()[-1].lower())
    return codes


def synth_description(item):
    """合成描述：description 优先，否则取首条知识文案，再否则取脚本名。
    末尾追加提取到的错误码（如 ORA-00600），使检查项可按错误码被关键词检索。"""
    desc = (item.get('description') or '').strip()
    if desc:
        base = desc[:300]
    else:
        kt = item.get('knowledge_text') or []
        base = ''
        for frag in kt:
            frag = (frag or '').strip()
            if frag:
                base = frag[:200]
                break
        if not base:
            base = item.get('name', '')
    codes = sorted(extract_error_codes(item))
    if codes:
        base = f"{base} [关联错误码: {' / '.join(codes)}]"
    return base[:500]


def load_catalog(dirpath):
    """读取目录下所有检查项目录 JSON"""
    items = []
    for f in sorted(os.listdir(dirpath)):
        if f.endswith('.json'):
            try:
                with open(os.path.join(dirpath, f), encoding='utf-8') as fh:
                    items.append(json.load(fh))
            except Exception as e:
                print(f'  跳过解析失败: {f} - {e}')
    return items


def main():
    parser = argparse.ArgumentParser(description='导入反编译运维检查项到知识图谱')
    parser.add_argument('--dir', default=os.environ.get('CHECK_ITEMS_JSON_DIR', ''),
                        help='检查项目录（JSON 目录）')
    parser.add_argument('--dry-run', action='store_true', help='只统计，不写库')
    args = parser.parse_args()

    if not args.dir or not os.path.isdir(args.dir):
        print('请指定 --dir <检查项目录>（或设置环境变量 CHECK_ITEMS_JSON_DIR）')
        return

    items = load_catalog(args.dir)
    print(f'读取检查项目录 {len(items)} 个')

    entities = []
    for item in items:
        name = (item.get('name') or '').strip()
        if not name:
            continue
        entities.append({
            'entity_type': 'check_item',
            'name': name,
            'normalized_name': name.lower(),
            'aliases': [],
            'description': synth_description(item),
            'properties': {
                'category': item.get('category', ''),
                'db_type': item.get('db_type', ''),
                'dangerous': item.get('dangerous', ''),
                'autorun': item.get('autorun', ''),
                'functions': item.get('functions', []),
                'sql': item.get('sql', []),
                'commands': item.get('commands', []),
                'knowledge_text': item.get('knowledge_text', []),
                'thresholds': item.get('thresholds', []),
            },
            'source_file_id': None,
            'confidence': 0.9,
            'extract_method': 'decompiled',
        })

    print(f'待导入 check_item 实体: {len(entities)}')
    if args.dry_run:
        print('dry-run 完成，未写库')
        return

    from db.kg_database import (
        save_entities_batch, save_relationships_batch, get_entities_by_type,
    )

    # 现有产品/错误码实体（用于建关系）
    products = {e['normalized_name']: e['id']
                for e in get_entities_by_type('database_product', limit=10000)}
    error_codes = {e['normalized_name']: e['id']
                   for e in get_entities_by_type('error_code', limit=10000)}

    emap = save_entities_batch(entities)
    print(f'check_item 实体已导入: {len(emap)} 个')

    rels = []
    for item in items:
        name = (item.get('name') or '').strip()
        eid = emap.get(('check_item', name.lower()))
        if not eid:
            continue
        prod = DB_TYPE_PRODUCT.get(item.get('db_type', ''))
        if prod and prod in products:
            rels.append({
                'from_entity_id': eid, 'to_entity_id': products[prod],
                'relation_type': 'applies_to', 'confidence': 0.9,
                'source_file_id': None, 'extract_method': 'decompiled',
            })
        for code in extract_error_codes(item):
            if code in error_codes:
                rels.append({
                    'from_entity_id': eid, 'to_entity_id': error_codes[code],
                    'relation_type': 'diagnoses', 'confidence': 0.8,
                    'source_file_id': None, 'extract_method': 'decompiled',
                })

    if rels:
        save_relationships_batch(rels)
    print(f'关系已建立: applies_to + diagnoses 共 {len(rels)} 条')


if __name__ == '__main__':
    main()
