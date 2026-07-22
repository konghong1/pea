import { Button, Tooltip } from 'antd';
import {
  BoldOutlined,
  ItalicOutlined,
  UnderlineOutlined,
  FontColorsOutlined,
  OrderedListOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';

interface Props {
  editorRef: React.RefObject<HTMLDivElement>;
}

/**
 * 富文本工具条 (T-M1-06, FR-M1-35)：加粗/斜体/下划线/颜色/有序/无序列表。
 * 作用在 contentEditable 编辑器上（execCommand）。
 */
export default function RichTextToolbar({ editorRef }: Props) {
  const exec = (cmd: string, value?: string) => {
    editorRef.current?.focus();
    document.execCommand(cmd, false, value);
  };

  const Btn = ({ title, onClick, children }: { title: string; onClick: () => void; children: React.ReactNode }) => (
    <Tooltip title={title}>
      <Button type="text" size="small" onClick={onClick} aria-label={title}>
        {children}
      </Button>
    </Tooltip>
  );

  return (
    <div className="mb-2 flex flex-wrap items-center gap-1 rounded-lg border border-black/10 bg-black/5 p-1 dark:border-white/10 dark:bg-white/5">
      <Btn title="加粗" onClick={() => exec('bold')}>
        <BoldOutlined />
      </Btn>
      <Btn title="斜体" onClick={() => exec('italic')}>
        <ItalicOutlined />
      </Btn>
      <Btn title="下划线" onClick={() => exec('underline')}>
        <UnderlineOutlined />
      </Btn>
      <Btn title="颜色" onClick={() => exec('foreColor', '#0984E3')}>
        <FontColorsOutlined />
      </Btn>
      <Btn title="有序列表" onClick={() => exec('insertOrderedList')}>
        <OrderedListOutlined />
      </Btn>
      <Btn title="无序列表" onClick={() => exec('insertUnorderedList')}>
        <UnorderedListOutlined />
      </Btn>
      <Btn title="标题" onClick={() => exec('formatBlock', 'H3')}>
        H
      </Btn>
      <Btn title="正文" onClick={() => exec('formatBlock', 'P')}>
        ¶
      </Btn>
    </div>
  );
}
