const THREE = require('three');
const { createNoise2D } = require('simplex-noise');
console.log('THREE resolved:', !!THREE);
console.log('THREE Version:', THREE.REVISION);
console.log('Simplex Noise resolved:', !!createNoise2D);
