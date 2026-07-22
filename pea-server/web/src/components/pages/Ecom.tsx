import { Steps, Tag } from 'antd';

/** M2 电商套图 —— 本期搁置占位，展示规划中的四步流程。 */
export default function Ecom() {
  return (
    <div className="pea-page">
      <div className="pea-page-pad">
        <div className="pea-hero-title">电商套图</div>
        <p className="pea-muted" style={{ marginTop: 8 }}>
          上传产品图 → AI 智能策划 → 一键生成主图 / 详情页整套。本期规划中。
        </p>
        <div style={{ marginTop: 28, maxWidth: 720 }}>
          <Steps
            direction="vertical"
            current={1}
            items={[
              { title: '上传产品图', description: '多视角图，建议 ≥3 张' },
              { title: '填写卖点 + 市场配置', description: 'USP / 平台 / 语种 / 风格' },
              { title: 'AI 智能策划出图规划', description: '主图 / 详情页 / 场景图' },
              { title: '一键生成套图', description: '消耗积分，结果入画廊' },
            ]}
          />
        </div>
        <div style={{ marginTop: 20 }}>
          <Tag color="purple">规划中</Tag>
        </div>
      </div>
    </div>
  );
}
