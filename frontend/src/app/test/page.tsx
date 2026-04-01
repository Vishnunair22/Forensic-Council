"use client";
import { useEffect, useState } from 'react';

export default function TestPage() {
  const [status, setStatus] = useState<string>('loading...');

  useEffect(() => {
    setStatus('OK — no three.js dependency');
  }, []);

  return (
    <div className="p-10 font-mono">
      <h1>System Test</h1>
      <p>Status: {status}</p>
    </div>
  );
}
