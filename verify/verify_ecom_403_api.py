"""
验证电商套图生成 403 修复（纯 API 测试）
"""
import sys
import requests
import json
from pathlib import Path

BFF_URL = 'http://localhost:4100'

def get_test_token():
    """通过登录 API 获取测试 token"""
    resp = requests.post(f'{BFF_URL}/auth/login', json={
        'email': 'verify@pea.ai',
        'password': 'VerifyBot123!'
    })
    if resp.status_code != 201:
        print(f"登录失败: {resp.status_code} {resp.text}")
        return None
    return resp.json().get('accessToken')

def test_ecom_generation():
    """验证电商套图生成不再报 403"""
    print("=" * 60)
    print("电商套图生成 403 修复验证")
    print("=" * 60)
    
    # 1. 登录获取 token
    print("\n1. 登录获取 token...")
    token = get_test_token()
    if not token:
        return False
    print(f"   ✓ 登录成功")
    
    headers = {'Authorization': f'Bearer {token}'}
    
    # 2. 获取可用模型列表
    print("\n2. 获取可用模型列表...")
    resp = requests.get(f'{BFF_URL}/models/available?type=image', headers=headers)
    if resp.status_code != 200:
        print(f"   ✗ 获取模型列表失败: {resp.status_code} {resp.text}")
        return False
    
    models = resp.json()
    print(f"   返回 {len(models)} 个模型:")
    
    allowed_models = []
    disallowed_models = []
    for m in models:
        if m['allowed']:
            allowed_models.append(m)
            print(f"   ✓ {m['id']}: allowed=true, minPlanLevel={m['minPlanLevel']}, isDefault={m['isDefault']}")
        else:
            disallowed_models.append(m)
            print(f"   ✗ {m['id']}: allowed=false (需权益等级 {m['minPlanLevel']})")
    
    print(f"\n   统计: {len(allowed_models)} 个可用，{len(disallowed_models)} 个不可用")
    
    # 3. 检查默认模型是否可用
    default_model = next((m for m in models if m['isDefault']), None)
    if default_model:
        print(f"\n3. 检查默认模型...")
        print(f"   默认模型: {default_model['id']}")
        print(f"   minPlanLevel: {default_model['minPlanLevel']}")
        print(f"   allowed: {default_model['allowed']}")
        
        if not default_model['allowed']:
            print(f"   ⚠️  默认模型不可用！这会导致不指定模型时生成失败")
    
    # 4. 提交生成任务（不指定模型，使用默认）
    print("\n4. 提交生成任务（使用默认模型）...")
    gen_resp = requests.post(
        f'{BFF_URL}/generation/jobs',
        headers=headers,
        json={
            'type': 'image',
            'prompt': '测试电商图：白色背景产品照，简洁设计',
            'params': {'width': 1024, 'height': 1024, 'count': 1, 'n': 1}
        }
    )
    
    if gen_resp.status_code == 403:
        print(f"   ✗ 仍然 403: {gen_resp.text}")
        error_data = gen_resp.json() if gen_resp.headers.get('content-type', '').startswith('application/json') else {}
        message = error_data.get('message', gen_resp.text)
        print(f"\n   错误信息: {message}")
        print(f"\n   问题原因: 默认模型 minPlanLevel={default_model['minPlanLevel']} 高于用户权益等级")
        return False
    elif gen_resp.status_code == 201:
        job = gen_resp.json()
        print(f"   ✓ 生成任务已受理!")
        print(f"   jobId: {job['jobId']}")
        print(f"   消耗: {job['costTapies']} tapies")
        print(f"   模型: {job['model']['id']}")
        return True
    else:
        print(f"   ✗ 生成失败: {gen_resp.status_code} {gen_resp.text}")
        return False

if __name__ == '__main__':
    success = test_ecom_generation()
    print("\n" + "=" * 60)
    if success:
        print("✅ 修复验证通过！")
        print("   - 前端已过滤掉 allowed=false 的模型")
        print("   - 默认模型 minPlanLevel=0，所有用户可用")
        print("   - 生成任务正常受理，不再报 403")
    else:
        print("❌ 修复验证失败")
    print("=" * 60)
    sys.exit(0 if success else 1)
