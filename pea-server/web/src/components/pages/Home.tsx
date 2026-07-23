import { useEffect, useState } from 'react';
import { Button, Spin, Empty } from 'antd';
import { PlusOutlined, FileTextOutlined } from '@ant-design/icons';
import { api } from '../../api/client';
import { useUi } from '../../store/ui';
import { useAuth } from '../../store/auth';
import { useCanvas } from '../../store/canvas';
import { toast } from '../../store/toast';

interface ProjectItem {
  id: number;
  title: string;
  version: number;
  node_count: number;
  updated_at: string;
}

const QUICK = [
  { label: '体验 Seedance 2.0 Mini', hint: '用一句话生成短视频' },
  { label: '建立项目创作记忆', hint: '让 Agent 记住你的偏好' },
  { label: '用一句话生成分镜脚本', hint: '从创意到成片' },
];

/** M3 主页 Workspace (T-M3-01)：欢迎 + 快捷操作 + 最近项目 + 新建。 */
export default function Home() {
  const setActive = useUi((s) => s.setActive);
  const { user } = useAuth();
  const openCanvas = useCanvas((s) => s.openCanvas);
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get('/canvases')
      .then((r) => setProjects(r.data ?? []))
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, []);

  const openProject = async (id: number) => {
    try {
      await openCanvas(id);
      setActive('canvas');
    } catch {
      toast.error('打开画布失败');
    }
  };

  const newProject = async () => {
    try {
      const { data } = await api.post('/canvases', { title: '未命名画布' });
      await openCanvas(data.id);
      setActive('canvas');
    } catch {
      toast.error('新建项目失败');
    }
  };

  return (
    <div className="pea-page">
      <div className="pea-page-pad">
        <div className="pea-hero-title">Hi，{user?.displayName ?? '创作者'} ✨</div>
        <p className="pea-muted" style={{ marginTop: 8 }}>
          一句话 + 画布节点编排，从创意到成片在一处闭环。
        </p>

        {/* 快捷操作 */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', margin: '20px 0' }}>
          {QUICK.map((q) => (
            <Button
              key={q.label}
              onClick={() => {
                setActive('canvas');
                toast.info(`已带入画布：${q.label}`);
              }}
            >
              {q.label}
            </Button>
          ))}
          <Button type="primary" icon={<PlusOutlined />} onClick={newProject}>
            新建项目
          </Button>
        </div>

        {/* 最近项目 */}
        <div className="pea-muted" style={{ marginTop: 8, fontWeight: 600, color: '#444' }}>
          最近项目
        </div>
        {loading ? (
          <div style={{ marginTop: 24 }}>
            <Spin />
          </div>
        ) : projects.length === 0 ? (
          <div style={{ marginTop: 24 }}>
            <Empty description="还没有项目，点击「新建项目」开始" />
          </div>
        ) : (
          <div className="pea-card-grid">
            {projects.map((p) => (
              <div
                key={p.id}
                className="pea-card"
                style={{ cursor: 'pointer' }}
                onClick={() => openProject(p.id)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <FileTextOutlined style={{ color: '#1fa2dc' }} />
                  <span style={{ fontWeight: 600 }}>{p.title}</span>
                </div>
                <div className="pea-muted" style={{ marginTop: 8, fontSize: 12 }}>
                  {p.node_count} 个节点 · 更新于 {new Date(p.updated_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
