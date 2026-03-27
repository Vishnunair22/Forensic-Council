"use client";
import * as THREE from 'three';
import { useEffect, useState } from 'react';

export default function TestPage() {
  const [version, setVersion] = useState<string>('loading...');

  useEffect(() => {
    setVersion(THREE.REVISION);
  }, []);

  return (
    <div className="p-10 font-mono">
      <h1>Three.js Resolution Test</h1>
      <p>Version: {version}</p>
    </div>
  );
}
