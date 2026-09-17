"""Independent stdlib PNG sample decoder/comparison. Ignore text metadata only.
Reject unsupported encodings and CRC corruption; preserve color interpretation.
"""
from pathlib import Path
import hashlib,struct,zlib

def decode(path):
 raw=Path(path).read_bytes();assert raw[:8]==b'\x89PNG\r\n\x1a\n';at=8;ids=b'';color={}
 while at<len(raw):
  n=struct.unpack('>I',raw[at:at+4])[0];kind=raw[at+4:at+8];data=raw[at+8:at+8+n]
  assert zlib.crc32(kind+data)&0xffffffff==struct.unpack('>I',raw[at+8+n:at+12+n])[0], 'PNG CRC error'
  if kind==b'IHDR':header=data
  if kind==b'IDAT':ids+=data
  if kind in [b'sRGB',b'gAMA',b'cHRM',b'iCCP']:color[kind.decode()]=data.hex()
  at+=12+n
 w,h,depth,kind,compression,filtration,interlace=struct.unpack('>IIBBBBB',header)
 assert depth==8 and kind in (2,6) and compression==filtration==interlace==0,'unsupported PNG encoding'
 bpp=3 if kind==2 else 4;stride=w*bpp;raw=zlib.decompress(ids);assert len(raw)==h*(stride+1)
 rows=[];prev=bytearray(stride);p=0
 for y in range(h):
  f=raw[p];p+=1;row=bytearray(raw[p:p+stride]);p+=stride
  for i in range(stride):
   a=row[i-bpp] if i>=bpp else 0;b=prev[i];c=prev[i-bpp] if i>=bpp else 0
   if f==0:predict=0
   elif f==1:predict=a
   elif f==2:predict=b
   elif f==3:predict=(a+b)//2
   elif f==4:
    q=a+b-c;pa,pb,pc=abs(q-a),abs(q-b),abs(q-c);predict=a if pa<=pb and pa<=pc else b if pb<=pc else c
   else:raise ValueError('unsupported filter')
   row[i]=(row[i]+predict)&255
  rows.append(bytes(row));prev=row
 return {'width':w,'height':h,'channels':bpp,'color':color},b''.join(rows)

def compare(a,b):
 ma,pa=decode(a);mb,pb=decode(b)
 return {'same_format_and_color':ma==mb,'equal_pixels':pa==pb,'pixel_sha256_a':hashlib.sha256(pa).hexdigest(),'pixel_sha256_b':hashlib.sha256(pb).hexdigest(),'differing_samples':sum(x!=y for x,y in zip(pa,pb)) if len(pa)==len(pb) else None,'max_sample_difference':max((abs(x-y) for x,y in zip(pa,pb)),default=0),'format_a':ma,'format_b':mb}
