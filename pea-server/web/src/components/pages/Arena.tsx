import { Button } from 'antd';
import { TrophyOutlined } from '@ant-design/icons';
import { toast } from '../../store/toast';

/**
 * 竞技场 (T-M4-03): PRD Non-Goal，明确移出 MVP 范围。
 * 保留导航占位并清晰说明范围，避免用户误认为缺陷。
 */
export default function Arena() {
  return (
    <div className="pea-page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center', maxWidth: 420 }}>
        <div className="pea-card" style={{ padding: 36 }}>
          <div style={{ fontSize: 48, marginBottom: 12, color: '#6c5ce7' }}>
            <TrophyOutlined />
          </div>
          <div className="pea-hero-title">创作竞技场</div>
          <p className="pea-muted" style={{ marginTop: 10 }}>
            竞技场（作品 PK / 投票排行）当前属于 PRD Non-Goals，已明确移出 MVP 范围，将在后续版本评估。
            当前你可以先用 TapTV 社区分享作品、收获点赞与收藏。
          </p>
          <Button
            type="primary"
            style={{ marginTop: 18 }}
            onClick={() => toast.info('前往「TapTV」即可发布与互动')}
          >
            去 TapTV 社区
          </Button>
        </div>
      </div>
    </div>
  );
}
