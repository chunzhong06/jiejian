// 以虚构内容生成可打开的测试文件；实际产物只写入运行数据目录。
import fs from 'node:fs';
import path from 'node:path';
function crc32(data) {let crc=0xffffffff;for(const byte of data){crc^=byte;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;}
function zip() {
  const name=Buffer.from('internal-notes.txt'),data=Buffer.from('FICTIONAL GALLERY TEAM MATERIALS\nWorking notes and original design draft.\n');
  const head=Buffer.alloc(30);head.writeUInt32LE(0x04034b50);head.writeUInt16LE(20,4);head.writeUInt32LE(crc32(data),14);head.writeUInt32LE(data.length,18);head.writeUInt32LE(data.length,22);head.writeUInt16LE(name.length,26);
  const central=Buffer.alloc(46);central.writeUInt32LE(0x02014b50);central.writeUInt16LE(20,4);central.writeUInt16LE(20,6);central.writeUInt32LE(crc32(data),16);central.writeUInt32LE(data.length,20);central.writeUInt32LE(data.length,24);central.writeUInt16LE(name.length,28);
  const end=Buffer.alloc(22);end.writeUInt32LE(0x06054b50);end.writeUInt16LE(1,8);end.writeUInt16LE(1,10);end.writeUInt32LE(central.length+name.length,12);end.writeUInt32LE(head.length+name.length+data.length,16);
  return Buffer.concat([head,name,data,central,name,end]);
}
function pdf() {
  const content='BT /F1 18 Tf 72 720 Td (Digital Gallery - Public Exhibition) Tj ET';
  const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',`<< /Length ${content.length} >>\nstream\n${content}\nendstream`];
  let body='%PDF-1.4\n';const offsets=[0];objects.forEach((obj,i)=>{offsets.push(Buffer.byteLength(body));body+=`${i+1} 0 obj\n${obj}\nendobj\n`;});const xref=Buffer.byteLength(body);
  body+=`xref\n0 6\n0000000000 65535 f \n`+offsets.slice(1).map(offset=>String(offset).padStart(10,'0')+' 00000 n \n').join('')+`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;return Buffer.from(body);
}
export function createAssets() {for(const [name,bytes] of [['internal.zip',zip()],['exhibition.pdf',pdf()]]){const file=path.join(process.env.JIEJIAN_DATA_DIR,name);fs.writeFileSync(file,bytes);}}
export function readAsset(name) {if(!['internal.zip','exhibition.pdf'].includes(name))throw new Error('unknown asset');return fs.readFileSync(path.join(process.env.JIEJIAN_DATA_DIR,name));}
