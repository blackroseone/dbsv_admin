#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DB Tool 综合测试脚本
测试所有后端 API 接口

使用方法:
    python test_all.py

环境变量:
    DB_TOOL_TEST_DB: 测试数据库路径（默认使用内存数据库）
"""

import os
import sys
import json
import unittest
import tempfile
import shutil

# 设置测试环境
os.environ['DB_TOOL_TEST_DB'] = ':memory:'

from app import create_app


class DBToolTestCase(unittest.TestCase):
    """DB Tool 综合测试类"""

    def setUp(self):
        """测试前准备"""
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

        # 创建临时目录用于测试文件上传
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """测试后清理"""
        # 清理临时目录
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    # ==================== 数据库类型测试 ====================

    def test_01_get_db_types(self):
        """测试获取数据库类型列表"""
        response = self.client.get('/api/db-types')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('types', data)
        self.assertIsInstance(data['types'], list)
        # 检查默认类型
        type_ids = [t['id'] for t in data['types']]
        self.assertIn('oracle', type_ids)
        self.assertIn('mysql', type_ids)

    def test_02_add_and_delete_db_type(self):
        """测试添加和删除数据库类型"""
        # 添加新类型
        response = self.client.post('/api/db-types',
                                    data=json.dumps({'id': 'testdb', 'name': '测试数据库', 'icon': '🧪'}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # 验证添加成功
        response = self.client.get('/api/db-types')
        data = json.loads(response.data)
        type_ids = [t['id'] for t in data['types']]
        self.assertIn('testdb', type_ids)

        # 删除类型
        response = self.client.delete('/api/db-types/testdb')
        self.assertEqual(response.status_code, 200)

        # 验证删除成功
        response = self.client.get('/api/db-types')
        data = json.loads(response.data)
        type_ids = [t['id'] for t in data['types']]
        self.assertNotIn('testdb', type_ids)

    # ==================== 知识库测试 ====================

    def test_03_knowledge_upload_and_list(self):
        """测试知识库文件上传和列表"""
        # 创建测试文件
        test_file = os.path.join(self.temp_dir, 'test.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('这是一个测试文件，用于测试知识库功能。')

        # 上传文件
        with open(test_file, 'rb') as f:
            response = self.client.post('/api/knowledge/upload/mysql',
                                          data={'file': (f, 'test.txt')},
                                          content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)

        # 获取文件列表
        response = self.client.get('/api/knowledge/files/mysql')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('files', data)
        filenames = [f['name'] for f in data['files']]
        self.assertIn('test.txt', filenames)

    def test_04_knowledge_search(self):
        """测试知识库搜索"""
        # 先上传文件
        test_file = os.path.join(self.temp_dir, 'search_test.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('MySQL 性能优化指南')

        with open(test_file, 'rb') as f:
            self.client.post('/api/knowledge/upload/mysql',
                               data={'file': (f, 'search_test.txt')},
                               content_type='multipart/form-data')

        # 搜索
        response = self.client.get('/api/knowledge/files/mysql?keyword=性能优化')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('files', data)

    def test_05_knowledge_preview(self):
        """测试知识库文件预览"""
        # 上传文件
        test_file = os.path.join(self.temp_dir, 'preview_test.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('预览测试内容')

        with open(test_file, 'rb') as f:
            self.client.post('/api/knowledge/upload/mysql',
                               data={'file': (f, 'preview_test.txt')},
                               content_type='multipart/form-data')

        # 预览
        response = self.client.get('/api/knowledge/preview/mysql/preview_test.txt')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('content', data)

    def test_06_knowledge_delete(self):
        """测试知识库文件删除"""
        # 上传文件
        test_file = os.path.join(self.temp_dir, 'delete_test.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('删除测试')

        with open(test_file, 'rb') as f:
            self.client.post('/api/knowledge/upload/mysql',
                               data={'file': (f, 'delete_test.txt')},
                               content_type='multipart/form-data')

        # 删除
        response = self.client.delete('/api/knowledge/delete/mysql/delete_test.txt')
        self.assertEqual(response.status_code, 200)

        # 验证删除
        response = self.client.get('/api/knowledge/files/mysql')
        data = json.loads(response.data)
        filenames = [f['name'] for f in data.get('files', [])]
        self.assertNotIn('delete_test.txt', filenames)

    # ==================== 收藏夹测试 ====================

    def test_07_favorites(self):
        """测试收藏夹功能"""
        # 先上传文件
        test_file = os.path.join(self.temp_dir, 'fav_test.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('收藏测试')

        with open(test_file, 'rb') as f:
            self.client.post('/api/knowledge/upload/mysql',
                               data={'file': (f, 'fav_test.txt')},
                               content_type='multipart/form-data')

        # 收藏
        response = self.client.post('/api/favorites',
                                      data=json.dumps({'db_type': 'mysql', 'filename': 'fav_test.txt'}),
                                      content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # 获取收藏
        response = self.client.get('/api/favorites')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('files', data)

    # ==================== 问答模板测试 ====================

    def test_08_qa_templates(self):
        """测试问答模板"""
        response = self.client.get('/api/qa/templates')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('templates', data)
        self.assertTrue(len(data['templates']) > 0)

    # ==================== SQL 工具测试 ====================

    def test_10_sql_format(self):
        """测试 SQL 格式化"""
        response = self.client.post('/api/sql/format',
                                      data=json.dumps({'sql': 'select * from users where id=1'}),
                                      content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('formatted_sql', data)

    def test_11_sql_review(self):
        """测试 SQL 审核"""
        response = self.client.post('/api/sql/review',
                                      data=json.dumps({
                                          'sql': 'SELECT * FROM users',
                                          'db_type': 'mysql'
                                      }),
                                      content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('review', data)

    def test_12_sql_convert(self):
        """测试 SQL 转换"""
        response = self.client.post('/api/sql/convert',
                                      data=json.dumps({
                                          'sql': 'SELECT * FROM users',
                                          'source_db': 'mysql',
                                          'target_db': 'oracle'
                                      }),
                                      content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('converted_sql', data)

    # ==================== 运维手册测试 ====================

    def test_13_manuals_upload_and_list(self):
        """测试运维手册上传和列表"""
        # 创建测试手册
        test_file = os.path.join(self.temp_dir, 'manual_test.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('运维手册测试内容')

        # 上传
        with open(test_file, 'rb') as f:
            response = self.client.post('/api/manuals',
                                          data={'file': (f, 'manual_test.txt')},
                                          content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)

        # 获取列表
        response = self.client.get('/api/manuals')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('manuals', data)

    # ==================== 命令速查测试 ====================

    def test_14_commands_get(self):
        """测试获取命令列表"""
        response = self.client.get('/api/commands?db_type=mysql')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('commands', data)

    def test_15_commands_category(self):
        """测试添加命令分类"""
        response = self.client.post('/api/commands/category',
                                      data=json.dumps({
                                          'db_type': 'mysql',
                                          'category_name': '测试分类'
                                      }),
                                      content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_16_commands_search(self):
        """测试命令搜索"""
        response = self.client.get('/api/commands/search?keyword=SELECT')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('results', data)

    # ==================== 集群拓扑测试 ====================

    def test_17_topology_cluster_crud(self):
        """测试集群增删改查"""
        # 创建集群
        response = self.client.post('/api/topology/clusters',
                                      data=json.dumps({
                                          'name': '测试集群',
                                          'db_type': 'mysql',
                                          'environment': 'development',
                                          'description': '测试用'
                                      }),
                                      content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        cluster_id = data.get('cluster', {}).get('id')
        self.assertIsNotNone(cluster_id)

        # 获取集群列表
        response = self.client.get('/api/topology/clusters')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('clusters', data)

        # 更新集群
        response = self.client.put(f'/api/topology/clusters/{cluster_id}',
                                     data=json.dumps({'name': '更新后的集群'}),
                                     content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # 删除集群
        response = self.client.delete(f'/api/topology/clusters/{cluster_id}')
        self.assertEqual(response.status_code, 200)

    def test_18_topology_server(self):
        """测试物理机管理"""
        # 先创建集群
        response = self.client.post('/api/topology/clusters',
                                      data=json.dumps({
                                          'name': '服务器测试集群',
                                          'db_type': 'mysql',
                                          'environment': 'development'
                                      }),
                                      content_type='application/json')
        data = json.loads(response.data)
        cluster_id = data.get('cluster', {}).get('id')

        # 添加物理机
        response = self.client.post(f'/api/topology/clusters/{cluster_id}/servers',
                                      data=json.dumps({
                                          'name': '测试服务器',
                                          'host': '192.168.1.1',
                                          'description': '测试用'
                                      }),
                                      content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # 清理
        self.client.delete(f'/api/topology/clusters/{cluster_id}')

    # ==================== 系统配置测试 ====================

    def test_19_config_llm(self):
        """测试 LLM 配置"""
        # 保存配置
        response = self.client.post('/api/config/llm',
                                      data=json.dumps({
                                          'api_url': 'https://api.example.com',
                                          'api_key': 'test-key',
                                          'model_name': 'gpt-4'
                                      }),
                                      content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # 获取配置
        response = self.client.get('/api/config/llm')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('api_url', data)

    def test_20_config_models(self):
        """测试多模型配置"""
        # 获取模型列表
        response = self.client.get('/api/config/llm/models')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('models', data)

    # ==================== 仪表盘测试 ====================

    def test_21_stats(self):
        """测试统计数据"""
        response = self.client.get('/api/stats')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('db_types_count', data)

    def test_22_health(self):
        """测试健康检查"""
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('status', data)

    def test_23_shortcuts(self):
        """测试快捷键"""
        response = self.client.get('/api/shortcuts')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('shortcuts', data)

    def test_24_tags(self):
        """测试标签"""
        response = self.client.get('/api/tags')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('tags', data)

    def test_25_logs(self):
        """测试操作日志"""
        response = self.client.get('/api/logs')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('logs', data)


class DBToolIntegrationTest(unittest.TestCase):
    """集成测试：模拟完整工作流程"""

    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_full_workflow(self):
        """测试完整工作流程"""
        # 1. 添加自定义数据库类型
        response = self.client.post('/api/db-types',
                                      data=json.dumps({'id': 'customdb', 'name': '自定义数据库', 'icon': '🔧'}),
                                      content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # 2. 上传知识库文件
        test_file = os.path.join(self.temp_dir, 'workflow_test.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write('这是一个完整工作流程测试文件。')

        with open(test_file, 'rb') as f:
            response = self.client.post('/api/knowledge/upload/customdb',
                                          data={'file': (f, 'workflow_test.txt')},
                                          content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)

        # 3. 创建集群
        response = self.client.post('/api/topology/clusters',
                                      data=json.dumps({
                                          'name': '工作流测试集群',
                                          'db_type': 'customdb',
                                          'environment': 'production'
                                      }),
                                      content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # 4. 配置 LLM
        response = self.client.post('/api/config/llm',
                                      data=json.dumps({
                                          'api_url': 'https://api.test.com',
                                          'api_key': 'test-key',
                                          'model_name': 'test-model'
                                      }),
                                      content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # 5. 验证统计数据
        response = self.client.get('/api/stats')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertGreaterEqual(data.get('db_types_count', 0), 1)

        # 6. 验证日志记录
        response = self.client.get('/api/logs')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('logs', data)


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(DBToolTestCase))
    suite.addTests(loader.loadTestsFromTestCase(DBToolIntegrationTest))

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 返回结果
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
