"use client";

import { useEffect, useRef } from "react";

/**
 * Shared glass background rendered once in the root layout.
 * Provides ambient gradient blobs, scanning grid, and crosshair effects
 * that show through transparent glass panels on every page.
 */
export function GlassBackground() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let rafId: number;
    const blobs = container.querySelectorAll<HTMLElement>("[data-parallax]");
    const crosshairs =
      container.querySelectorAll<HTMLElement>("[data-crosshair]");

    const handleScroll = () => {
      const scroll = window.scrollY;
      blobs.forEach((blob) => {
        const factor = parseFloat(blob.dataset.parallax || "0");
        blob.style.transform = `translateY(${scroll * factor}px)`;
      });
    };

    const handleMouse = (e: MouseEvent) => {
      const cx = (e.clientX / window.innerWidth - 0.5) * 20;
      const cy = (e.clientY / window.innerHeight - 0.5) * 20;
      crosshairs.forEach((ch) => {
        const speed = parseFloat(ch.dataset.crosshair || "1");
        ch.style.transform = `translate(${cx * speed}px, ${cy * speed}px)`;
      });
    };

    const onScroll = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(handleScroll);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("mousemove", handleMouse, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("mousemove", handleMouse);
      cancelAnimationFrame(rafId);
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 pointer-events-none"
      aria-hidden="true"
      style={{ zIndex: 0 }}
    >
      {/* Base dark */}
      <div className="absolute inset-0" style={{ background: "#080C14" }} />

      {/* Ambient gradient blobs */}
      <div
        className="absolute"
        data-parallax="-0.1"
        style={{
          top: "-10%",
          left: "8%",
          width: 700,
          height: 700,
          background:
            "radial-gradient(circle, rgba(79,70,229,0.18) 0%, transparent 70%)",
          filter: "blur(100px)",
        }}
      />
      <div
        className="absolute"
        data-parallax="-0.06"
        style={{
          top: "30%",
          right: "5%",
          width: 560,
          height: 560,
          background:
            "radial-gradient(circle, rgba(13,148,136,0.14) 0%, transparent 70%)",
          filter: "blur(80px)",
        }}
      />
      <div
        className="absolute"
        data-parallax="-0.04"
        style={{
          bottom: "10%",
          left: "30%",
          width: 480,
          height: 480,
          background:
            "radial-gradient(circle, rgba(34,211,238,0.08) 0%, transparent 70%)",
          filter: "blur(90px)",
        }}
      />

      {/* Evidence scanning grid */}
      <div className="microscope-evidence-grid" />

      {/* Horizontal scan lines */}
      <div
        className="microscope-scanline"
        style={
          {
            top: "15%",
            "--scan-duration": "7s",
            "--scan-delay": "0s",
          } as React.CSSProperties
        }
      />
      <div
        className="microscope-scanline"
        style={
          {
            top: "45%",
            "--scan-duration": "10s",
            "--scan-delay": "3s",
          } as React.CSSProperties
        }
      />
      <div
        className="microscope-scanline"
        style={
          {
            top: "75%",
            "--scan-duration": "12s",
            "--scan-delay": "6s",
          } as React.CSSProperties
        }
      />

      {/* Crosshair markers — mouse-reactive */}
      <div
        className="microscope-crosshair"
        data-crosshair="1"
        style={
          {
            top: "20%",
            left: "15%",
            "--crosshair-size": "100px",
            "--pulse-duration": "5s",
            "--pulse-delay": "0s",
          } as React.CSSProperties
        }
      />
      <div
        className="microscope-crosshair"
        data-crosshair="-1"
        style={
          {
            top: "60%",
            right: "20%",
            "--crosshair-size": "80px",
            "--pulse-duration": "6s",
            "--pulse-delay": "2s",
          } as React.CSSProperties
        }
      />
      <div
        className="microscope-crosshair"
        data-crosshair="0.5"
        style={
          {
            bottom: "25%",
            left: "50%",
            "--crosshair-size": "140px",
            "--pulse-duration": "7s",
            "--pulse-delay": "4s",
          } as React.CSSProperties
        }
      />

      {/* Subtle dot grid overlay */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(rgba(34,211,238,0.04) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />

      {/* Bottom fade for depth */}
      <div
        className="absolute inset-x-0 bottom-0 h-1/3"
        style={{
          background: "linear-gradient(to top, rgba(8,12,20,0.6), transparent)",
        }}
      />
    </div>
  );
}
