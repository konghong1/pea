import { CheckCircleFilled, InfoCircleFilled, ExclamationCircleFilled, CloseCircleFilled } from '@ant-design/icons';
import { useToast, ToastLevel } from '../store/toast';

const ICONS: Record<ToastLevel, React.ReactNode> = {
  info: <InfoCircleFilled style={{ color: '#00CEC9' }} />,
  success: <CheckCircleFilled style={{ color: '#52c41a' }} />,
  warning: <ExclamationCircleFilled style={{ color: '#faad14' }} />,
  error: <CloseCircleFilled style={{ color: '#ff4d4f' }} />,
};

/** 全局轻提示容器：固定顶部居中，堆叠不重叠 (FR-G4)。 */
export default function Toast() {
  const items = useToast((s) => s.items);
  const dismiss = useToast((s) => s.dismiss);
  return (
    <div className="pea-toast-wrap">
      {items.map((t) => (
        <div
          key={t.id}
          className={`pea-toast pea-toast-${t.level}${t.leaving ? ' pea-toast-leaving' : ''}`}
          onClick={() => dismiss(t.id)}
        >
          <span className="pea-toast-icon">{ICONS[t.level]}</span>
          <span className="pea-toast-text">{t.content}</span>
        </div>
      ))}
    </div>
  );
}
