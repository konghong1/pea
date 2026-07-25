"""
验证电商套图生成 403 修复
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright, expect

BASE_URL = 'http://localhost:8088'
BFF_URL = 'http://localhost:4100'

def test_ecom_generation():
    """验证电商套图生成不再报 403"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        
        # 1. 登录
        print("1. 登录...")
        page.goto(f'{BASE_URL}/login')
        page.fill('input[name="email"]', 'verify@pea.ai')
        page.fill('input[name="password"]', 'VerifyBot123!')
        page.click('button[type="submit"]')
        page.wait_for_url('**/workspace', timeout=10000)
        
        # 2. 获取 token
        token = page.evaluate('localStorage.getItem("pea_token")')
        assert token, '登录失败：未获取到 token'
        print(f"   ✓ 登录成功，token={token[:20]}...")
        
        # 3. 调用 BFF API 获取模型列表
        print("\n2. 获取可用模型列表...")
        import requests
        headers = {'Authorization': f'Bearer {token}'}
        
        resp = requests.get(f'{BFF_URL}/models/available?type=image', headers=headers)
        assert resp.status_code == 200, f'获取模型列表失败: {resp.status_code} {resp.text}'
        models = resp.json()
        print(f"   返回 {len(models)} 个模型:")
        for m in models:
            print(f"   - {m['id']}: allowed={m['allowed']}, minPlanLevel={m['minPlanLevel']}, isDefault={m['isDefault']}")
        
        # 4. 验证只有 allowed=true 的模型显示
        allowed_models = [m for m in models if m['allowed']]
        disallowed_models = [m for m in models if not m['allowed']]
        print(f"\n   ✓ 可用模型: {len(allowed_models)} 个")
        if disallowed_models:
            print(f"   ⚠  不可用模型（前端应隐藏）: {len(disallowed_models)} 个")
            for m in disallowed_models:
                print(f"     - {m['id']} (需权益等级 {m['minPlanLevel']})")
        
        # 5. 提交生成任务（使用默认模型，应该成功）
        print("\n3. 提交生成任务...")
        gen_resp = requests.post(
            f'{BFF_URL}/generation/jobs',
            headers=headers,
            json={
                'type': 'image',
                'prompt': '测试电商图：白色背景产品照',
                'params': {'width': 1024, 'height': 1024, 'count': 1, 'n': 1}
            }
        )
        
        if gen_resp.status_code == 403:
            print(f"   ✗ 仍然 403: {gen_resp.text}")
            print("   这表明默认模型不是 min_plan_level=0 的模型")
            
            # 检查默认模型
            default_model = next((m for m in models if m['isDefault']), None)
            if default_model:
                print(f"   当前默认模型: {default_model['id']} (minPlanLevel={default_model['minPlanLevel']})")
            return False
        elif gen_resp.status_code == 201:
            job = gen_resp.json()
            print(f"   ✓ 生成任务已受理: jobId={job['jobId']}, cost={job['costTapies']} tapies")
            print(f"   使用模型: {job['model']['id']}")
            return True
        else:
            print(f"   ✗ 生成失败: {gen_resp.status_code} {gen_resp.text}")
            return False
        
        browser.close()

if __name__ == '__main__':
    success = test_ecom_generation()
    sys.exit(0 if success else 1)
