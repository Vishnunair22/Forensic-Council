"use client";

import { useRef } from "react";
import { FileCheck2, Loader2, UploadCloud, X } from "lucide-react";
import clsx from "clsx";
import { ALLOWED_MIME_TYPES } from "@/lib/constants";

interface FileUploadSectionProps {
  file: File | null;
  isDragging: boolean;
  isUploading: boolean;
  validationError: string | null;
  onFileSelect: (file: File) => void;
  onFileDrop: (event: React.DragEvent<HTMLElement>) => void;
  onDragEnter: (event: React.DragEvent<HTMLElement>) => void;
  onDragLeave: (event: React.DragEvent<HTMLElement>) => void;
  onUpload: (file: File) => void;
  onClear: () => void;
}

export function FileUploadSection({
  file,
  isDragging,
  isUploading,
  validationError,
  onFileSelect,
  onFileDrop,
  onDragEnter,
  onDragLeave,
  onUpload,
  onClear,
}: FileUploadSectionProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const openPicker = () => inputRef.current?.click();

  return (
    <section className="w-full" aria-label="Evidence upload">
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload evidence file"
        aria-describedby={validationError ? "file-upload-error" : "file-upload-help"}
        onClick={openPicker}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            openPicker();
          }
        }}
        onDrop={onFileDrop}
        onDragEnter={onDragEnter}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={onDragLeave}
        className={clsx(
          "relative rounded-2xl border border-dashed p-8 text-center transition-colors",
          "bg-surface-1/70 text-slate-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]",
          isDragging ? "border-primary bg-primary/10" : "border-white/20 hover:border-primary/60",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          className="sr-only"
          accept={Array.from(ALLOWED_MIME_TYPES).join(",")}
          onChange={(event) => {
            const selected = event.target.files?.[0];
            if (selected) onFileSelect(selected);
          }}
        />

        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full border border-primary/30 bg-primary/10">
          {file ? <FileCheck2 className="h-7 w-7 text-success-light" /> : <UploadCloud className="h-7 w-7 text-primary-soft" />}
        </div>

        <h2 className="text-xl font-bold text-white">{file ? file.name : "Upload Evidence"}</h2>
        <p id="file-upload-help" className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-300">
          Drag & drop or click to browse. Supports image, video, audio, and metadata evidence.
        </p>

        {validationError && (
          <p id="file-upload-error" role="alert" className="mt-4 text-sm font-semibold text-rose-200">
            {validationError}
          </p>
        )}
      </div>

      {file && (
        <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:justify-center">
          <button
            type="button"
            onClick={() => onUpload(file)}
            disabled={isUploading}
            className="btn-horizon-primary min-h-12"
          >
            {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {isUploading ? "Processing Evidence" : "Begin Analysis"}
          </button>
          <button
            type="button"
            onClick={onClear}
            disabled={isUploading}
            className="btn-horizon-outline min-h-12"
          >
            <X className="h-4 w-4" />
            Clear File
          </button>
        </div>
      )}
    </section>
  );
}
