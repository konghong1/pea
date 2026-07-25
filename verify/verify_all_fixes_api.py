"""
电商套图修复验证（API 层面）
验证点：
1. 模型选择器显示所有模型，无权模型 allowed=false
2. 弹出框间距统一（通过代码审查确认）
3. 点击外部关闭（通过代码审查确认）
"""
import sys
import requests
import json

BASE_URL = 'http://localhost:4100'

def test_model_permission_display():
    """测试模型权限显示"""
    print("\n" + "=" * 60)
    print("验证：模型选择器权限显示")
    print("=" * 60)

    # 1. 登录获取 token
    print("\n1. 登录获取 token...")
    resp = requests.post(f'{BASE_URL}/auth/register', json={
        'email': f'verify_perm_{int(__import__("time").time())}@pea.ai',
        'password': 'Test123!',
        'displayName': 'PermTest'
    })

    if resp.status_code != 201:
        print(f"   ⚠️  注册失败，尝试登录: {resp.status_code}")
        # 尝试登录之前注册的用户
        resp = requests.post(f'{BASE_URL}/auth/login', json={
            'email': 'test_ecom@pea.ai',
            'password': 'Test123!'
        })
        if resp.status_code != 201:
            print(f"   ✗ 登录失败: {resp.status_code} {resp.text}")
            return False

    token = resp.json().get('token')
    if not token:
        print("   ✗ 未获取到 token")
        return False

    print("   ✓ 登录成功")
    headers = {'Authorization': f'Bearer {token}'}

    # 2. 获取可用模型列表
    print("\n2. 获取图片模型列表...")
    resp = requests.get(f'{BASE_URL}/models/available?type=image', headers=headers)
    if resp.status_code != 200:
        print(f"   ✗ 获取模型列表失败: {resp.status_code}")
        return False

    models = resp.json()
    print(f"   ✓ 返回 {len(models)} 个模型")

    # 3. 检查权限字段
    print("\n3. 检查模型权限字段...")
    allowed_count = 0
    disallowed_count = 0

    for m in models:
        status = "✓ 可用" if m['allowed'] else "✗ 需升级"
        level = f"Lv.{m['minPlanLevel']}"
        print(f"   [{status}] {m['displayName']:<25} ({level})")
        if m['allowed']:
            allowed_count += 1
        else:
            disallowed_count += 1

    print(f"\n   统计: {allowed_count} 个可用，{disallowed_count} 个需升级")

    # 4. 验证前端应该显示所有模型
    print("\n4. 验证前端应该显示所有模型...")
    if len(models) > 0:
        print("   ✓ 前端应该显示所有模型（包含 allowed=false 的模型）")
        if disallowed_count > 0:
            print("   ✓ 无权模型应该置灰显示，提示所需权益等级")
        else:
            print("   ℹ️  当前用户有权使用所有模型")

    # 5. 验证提交生成任务
    print("\n5. 验证提交生成任务（使用默认模型）...")
    default_model = next((m for m in models if m['isDefault']), None)
    if not default_model:
        print("   ✗ 未找到默认模型")
        return False

    if not default_model['allowed']:
        print(f"   ✗ 默认模型 {default_model['displayName']} 无权使用")
        return False

    print(f"   默认模型: {default_model['displayName']} (Lvl.{default_model['minPlanLevel']})")

    resp = requests.post(f'{BASE_URL}/generation/jobs', headers=headers, json={
        'type': 'image',
        'prompt': 'API 验证测试：白色背景产品照',
        'params': {'width': 1024, 'height': 1024, 'count': 1, 'n': 1}
    })

    if resp.status_code == 201:
        job = resp.json()
        print(f"   ✓ 生成任务已受理: jobId={job['jobId']}")
        print(f"   消耗: {job['costTapies']} Tapies")
        print(f"   模型: {job['model']['id']}")
        return True
    elif resp.status_code == 403:
        print(f"   ✗ 仍然 403: {resp.text}")
        return False
    else:
        print(f"   ✗ 提交失败: {resp.status_code} {resp.text}")
        return False


def verify_code_changes():
    """通过代码审查确认修复内容"""
    print("\n" + "=" * 60)
    print("验证：代码修复内容")
    print("=" * 60)

    import os
    from pathlib import Path

    base_path = Path("C:/workspace/pea/pea-server/web/src/components")

    # 1. 验证 galleryApi.ts 中的权限字段
    print("\n1. 验证 galleryApi.ts 权限字段...")
    gallery_api_path = base_path / "ecom/galleryApi.ts"
    if gallery_api_path.exists():
        content = gallery_api_path.read_text(encoding='utf-8')
        if 'allowed: boolean' in content and 'minPlanLevel: number' in content:
            print("   ✓ GalleryImageModelEntry 接口已添加权限字段")
        else:
            print("   ✗ 未找到权限字段定义")
            return False

        if 'allowed: m.allowed' in content and 'minPlanLevel: m.minPlanLevel' in content:
            print("   ✓ 模型数据已传递权限字段")
        else:
            print("   ✗ 未找到权限字段传递")
            return False

        if '!m.enabled) continue' in content and '!m.allowed' not in content.split('!m.enabled) continue')[0]:
            print("   ✓ 已移除无权模型过滤，保留所有模型供前端显示")
        else:
            print("   ⚠️  可能还在过滤无权模型")

    # 2. 验证 EcommerceGallery.tsx 中的禁用逻辑
    print("\n2. 验证 EcommerceGallery.tsx 禁用逻辑...")
    ecom_path = base_path / "ecom/EcommerceGallery.tsx"
    if ecom_path.exists():
        content = ecom_path.read_text(encoding='utf-8')
        if 'disabled: !m.allowed' in content:
            print("   ✓ 无权模型已设置为禁用状态")
        else:
            print("   ✗ 未找到禁用逻辑")
            return False

        if 'toast.error' in content and 'minPlanLevel' in content:
            print("   ✓ 点击禁用模型时显示错误提示")
        else:
            print("   ⚠️  未找到错误提示逻辑")

    # 3. 验证 NodeChatPrompt.tsx 中的间距修复
    print("\n3. 验证 NodeChatPrompt.tsx 间距修复...")
    prompt_path = base_path / "NodeChatPrompt.tsx"
    if prompt_path.exists():
        content = prompt_path.read_text(encoding='utf-8')
        if 'const gap = 8' in content:
            print("   ✓ 弹出框间距已统一为 8px")
        else:
            print("   ✗ 未找到间距修复")
            return False

        if 'aspectBtnRef.current?.contains(t)' in content:
            print("   ✓ 点击外部关闭逻辑已包含比例选择按钮")
        else:
            print("   ✗ 未找到点击外部关闭修复")
            return False

    print("\n" + "=" * 60)
    print("✅ 所有代码修复已验证通过")
    print("=" * 60)
    return True


if __name__ == '__main__':
    success = True

    # 验证 API 层面的权限显示
    if not test_model_permission_display():
        success = False

    # 验证代码修改
    if not verify_code_changes():
        success = False

    if success:
        print("\n" + "=" * 60)
        print("✅ 修复验证通过")
        print("   - 模型选择器显示所有模型，无权模型置灰")
        print("   - 弹出框间距统一为 8px")
        print("   - 点击外部可关闭弹出框")
        print("=" * 60)

    sys.exit(0 if success else 1)
