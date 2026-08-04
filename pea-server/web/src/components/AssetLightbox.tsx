import { useEffect, useCallback, useState } from 'react';
import { createPortal } from 'react-dom';
import { CloseOutlined } from '@ant-design/icons';
import { getFileUrl } from '../api/files';
import type { Asset } from '../api/assets';

interface AssetLightboxProps {
  asset: Asset | null;
  onClose: () => void;
}

export default function AssetLightbox({ asset, onClose }: AssetLightboxProps) {
  const [src, setSrc] = useState(asset?.url ?? '');

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose],
  );

  useEffect(() => {
    setSrc(asset?.url ?? '');
  }, [asset?.url]);

  useEffect(() => {
    if (!asset) return;
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [asset, handleKeyDown]);

  const handleError = useCallback(async () => {
    if (!asset) return;
    try {
      const blobUrl = await getFileUrl(asset.object_key);
      if (blobUrl) setSrc(blobUrl);
    } catch {
      // 兜底失败则保留占位
    }
  }, [asset]);

  if (!asset) return null;

  const isImage = /^image\//.test(asset.content_type);
  const isVideo = /^video\//.test(asset.content_type);
  const canPreview = isImage || isVideo;
  if (!canPreview) return null;

  return createPortal(
    <div
      className="pea-asset-lightbox"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={`${asset.name} 预览`}
    >
      <button
        type="button"
        className="pea-asset-lightbox-close"
        onClick={onClose}
        aria-label="关闭"
      >
        <CloseOutlined />
      </button>
      <div className="pea-asset-lightbox-content">
        {isImage ? (
          <img src={src} alt={asset.name} onError={handleError} />
        ) : (
          <video src={src} controls autoPlay loop muted={false} onError={handleError} />
        )}
      </div>
      <div className="pea-asset-lightbox-name">{asset.name}</div>
    </div>,
    document.body,
  );
}
