"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";
import { forwardRef, type ReactNode } from "react";

export interface OverlayProps {
  isOpen: boolean;
  onClose?: () => void;
  children: ReactNode;
  className?: string;
  showCloseButton?: boolean;
  closeOnEscape?: boolean;
  closeOnOutsideClick?: boolean;
}

/**
 * Overlay - Shared modal overlay with focus trap for accessibility.
 *
 * Uses Radix Dialog for:
 * - Focus trap (keyboard users cannot tab outside)
 * - Focus restoration on close
 * - Escape key to close
 * - Screen reader announcements
 *
 * Usage:
 * <Overlay isOpen={show} onClose={() => setShow(false)}>
 *   <YourContent />
 * </Overlay>
 */
export const Overlay = forwardRef<HTMLDivElement, OverlayProps>(
  function Overlay(
    { isOpen, onClose, children, className, showCloseButton = true, closeOnEscape = true, closeOnOutsideClick = true },
    ref,
  ) {
    return (
      <AnimatePresence>
        {isOpen && (
          <Dialog.Root open={isOpen} onOpenChange={(open) => !open && onClose?.()}>
            <Dialog.Portal forceMount>
              <Dialog.Overlay asChild>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0, transition: { duration: 0.18, ease: "easeOut" } }}
                  transition={{ duration: 0.12, ease: "easeOut" }}
                  className={clsx(
                    "fixed inset-0 z-[10000] flex items-center justify-center px-6",
                    "bg-black/80 backdrop-blur-md",
                    className,
                  )}
                  style={{ background: "rgba(0, 0, 0, 0.95)", backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)" }}
                >
                  <Dialog.Title hidden>Overlay dialog</Dialog.Title>
                  <Dialog.Description hidden>
                    Modal overlay for forensic analysis interaction.
                  </Dialog.Description>
                  <Dialog.Content
                    ref={ref}
                    onEscapeKeyDown={(e) => !closeOnEscape && e.preventDefault()}
                    onPointerDownOutside={(e) => !closeOnOutsideClick && e.preventDefault()}
                    className="relative w-full max-w-md"
                    style={{ outline: "none" }}
                  >
                    {showCloseButton && (
                      <Dialog.Close asChild>
                        <button
                          type="button"
                          aria-label="Close overlay"
                          className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 transition-colors text-white/70 hover:text-white"
                        >
                          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M12 4L4 12M4 4l8 8" />
                          </svg>
                        </button>
                      </Dialog.Close>
                    )}
                    {children}
                  </Dialog.Content>
                </motion.div>
              </Dialog.Overlay>
            </Dialog.Portal>
          </Dialog.Root>
        )}
      </AnimatePresence>
    );
  },
);

Overlay.displayName = "Overlay";