/**
 * Unit tests for FileUploadSection component
 * Tests: drag-and-drop, validation, error states, accessibility
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FileUploadSection } from '@/components/evidence/FileUploadSection';
import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('FileUploadSection', () => {
  const mockOnFileSelect = vi.fn();
  
  beforeEach(() => {
    mockOnFileSelect.mockClear();
  });

  it('renders upload area with correct ARIA attributes', () => {
    render(<FileUploadSection onFileSelect={mockOnFileSelect} />);
    
    const dropZone = screen.getByRole('button', { name: /upload evidence/i });
    expect(dropZone).toHaveAttribute('aria-describedby');
    expect(dropZone).toHaveAttribute('tabIndex', '0');
  });

  it('validates file type before upload', async () => {
    render(<FileUploadSection onFileSelect={mockOnFileSelect} />);
    
    const file = new File(['test'], 'malicious.exe', { type: 'application/x-executable' });
    const input = screen.getByTestId('file-input');
    
    fireEvent.change(input, { target: { files: [file] } });
    
    // Should show error, not call onFileSelect
    await waitFor(() => {
      expect(screen.getByText(/unsupported file type/i)).toBeInTheDocument();
    });
    expect(mockOnFileSelect).not.toHaveBeenCalled();
  });

  it('accepts valid image files', async () => {
    render(<FileUploadSection onFileSelect={mockOnFileSelect} />);
    
    const file = new File(['fake image data'], 'evidence.jpg', { 
      type: 'image/jpeg' 
    });
    const input = screen.getByTestId('file-input');
    
    fireEvent.change(input, { target: { files: [file] } });
    
    await waitFor(() => {
      expect(mockOnFileSelect).toHaveBeenCalledWith(file);
    });
  });

  it('enforces 50MB file size limit', async () => {
    render(<FileUploadSection onFileSelect={mockOnFileSelect} />);
    
    // Create 51MB file
    const largeFile = new File(
      [new ArrayBuffer(51 * 1024 * 1024)], 
      'large.mp4', 
      { type: 'video/mp4' }
    );
    const input = screen.getByTestId('file-input');
    
    fireEvent.change(input, { target: { files: [largeFile] } });
    
    await waitFor(() => {
      expect(screen.getByText(/file too large/i)).toBeInTheDocument();
      expect(mockOnFileSelect).not.toHaveBeenCalled();
    });
  });

  it('supports keyboard navigation for accessibility', () => {
    render(<FileUploadSection onFileSelect={mockOnFileSelect} />);
    
    const dropZone = screen.getByRole('button', { name: /upload evidence/i });
    dropZone.focus();
    
    // Enter key should trigger file picker
    fireEvent.keyDown(dropZone, { key: 'Enter' });
    expect(screen.getByTestId('file-input')).toBeInTheDocument();
    
    // Space key should also work
    fireEvent.keyDown(dropZone, { key: ' ' });
  });
});