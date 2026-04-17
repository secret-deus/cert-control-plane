import { useCallback, useState } from 'react';
import { Upload, FileText, AlertCircle } from 'lucide-react';

interface FileUploadZoneProps {
  onFileSelect: (file: File) => void;
  accept?: string;
  maxSize?: number;
  disabled?: boolean;
}

const ACCEPTED_FORMATS = '.zip,.tar.gz,.tgz';
const MAX_SIZE_MB = 10;

export default function FileUploadZone({
  onFileSelect,
  accept = ACCEPTED_FORMATS,
  maxSize = MAX_SIZE_MB * 1024 * 1024,
  disabled = false,
}: FileUploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const validateFile = useCallback(
    (file: File): string | null => {
      const lowered = file.name.toLowerCase();
      if (
        !lowered.endsWith('.zip') &&
        !lowered.endsWith('.tar.gz') &&
        !lowered.endsWith('.tgz')
      ) {
        return '仅支持 .zip、.tar.gz、.tgz 格式';
      }

      if (file.size > maxSize) {
        return `文件大小不能超过 ${MAX_SIZE_MB}MB`;
      }

      return null;
    },
    [maxSize]
  );

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setIsDragging(false);
      setError(null);

      if (disabled) return;

      const file = event.dataTransfer.files[0];
      if (!file) return;

      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }

      setSelectedFile(file);
      onFileSelect(file);
    },
    [disabled, validateFile, onFileSelect]
  );

  const handleDragOver = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      if (!disabled) {
        setIsDragging(true);
      }
    },
    [disabled]
  );

  const handleDragLeave = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(false);
  }, []);

  const handleInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      setError(null);
      const file = event.target.files?.[0];
      if (!file) return;

      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }

      setSelectedFile(file);
      onFileSelect(file);
    },
    [validateFile, onFileSelect]
  );

  return (
    <div className="space-y-3">
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`relative rounded-lg border-2 border-dashed p-8 transition-colors ${
          isDragging
            ? 'border-[rgba(255,153,92,0.24)] bg-[rgba(255,153,92,0.06)]'
            : 'border-white/8 bg-white/[0.02]'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-white/15'}`}
      >
        <input
          type="file"
          accept={accept}
          onChange={handleInputChange}
          disabled={disabled}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
        />

        <div className="text-center">
          <div className="mx-auto w-12 h-12 rounded-full border border-white/10 bg-white/[0.03] flex items-center justify-center text-slate-400">
            <Upload size={20} />
          </div>
          <div className="mt-4 text-sm text-slate-300">
            {selectedFile ? (
              <div className="flex items-center justify-center gap-2">
                <FileText size={14} className="text-[#ffbf8f]" />
                <span className="font-medium text-white">{selectedFile.name}</span>
              </div>
            ) : (
              <>
                <span className="font-medium text-white">点击选择文件</span>
                <span className="text-slate-400"> 或拖拽到此处</span>
              </>
            )}
          </div>
          <p className="mt-2 text-xs text-slate-500">
            支持 .zip、.tar.gz、.tgz 格式，最大 {MAX_SIZE_MB}MB
          </p>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-[18px] border border-[rgba(255,153,92,0.18)] bg-[rgba(255,153,92,0.10)] p-3 text-sm text-[#ffbf8f]">
          <AlertCircle size={14} />
          {error}
        </div>
      )}
    </div>
  );
}
