import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Button, Form, Input, Card, Typography } from 'antd';
import { api } from '../api/client';
import { useAuth } from '../store/auth';

export default function Login() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [loading, setLoading] = useState(false);
  const setAuth = useAuth((s) => s.setAuth);
  const navigate = useNavigate();
  const { message } = App.useApp();

  const onFinish = async (v: { email: string; password: string; displayName?: string }) => {
    setLoading(true);
    try {
      const url = mode === 'login' ? '/auth/login' : '/auth/register';
      const { data } = await api.post(url, v);
      setAuth(data.token, data.user);
      message.success(mode === 'login' ? '登录成功' : '注册成功');
      navigate('/');
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '操作失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full items-center justify-center bg-gradient-to-br from-pea-brand/10 to-pea-accent/10">
      <Card className="w-[380px] shadow-xl">
        <Typography.Title level={3} className="!mb-1">
          pea Creative OS
        </Typography.Title>
        <Typography.Text type="secondary">
          {mode === 'login' ? '登录以继续创作' : '创建你的工作区'}
        </Typography.Text>
        <Form layout="vertical" className="mt-4" onFinish={onFinish}>
          <Form.Item label="邮箱" name="email" rules={[{ required: true, type: 'email' }]}>
            <Input placeholder="you@pea.ai" />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true, min: 8 }]}>
            <Input.Password placeholder="至少 8 位" />
          </Form.Item>
          {mode === 'register' && (
            <Form.Item label="昵称" name="displayName">
              <Input placeholder="可选" />
            </Form.Item>
          )}
          <Button type="primary" htmlType="submit" block loading={loading}>
            {mode === 'login' ? '登录' : '注册'}
          </Button>
        </Form>
        <Button
          type="link"
          className="mt-2"
          onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
        >
          {mode === 'login' ? '没有账号？去注册' : '已有账号？去登录'}
        </Button>
      </Card>
    </div>
  );
}
