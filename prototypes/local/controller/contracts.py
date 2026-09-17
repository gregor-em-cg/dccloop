"""Strict validator for the frozen schema subset; no external dependencies."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import math
import re

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schemas/stage1-v1.schema.json').read_text())

class ContractError(ValueError):
    pass

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def validate(value, name=None, schema=None, path='$'):
    schema = schema if schema is not None else SCHEMA['$defs'][name]
    if '$ref' in schema:
        return validate(value, schema=SCHEMA['$defs'][schema['$ref'].split('/')[-1]], path=path)
    if 'const' in schema and value != schema['const']:
        raise ContractError(f'{path}: expected constant {schema["const"]!r}')
    if 'enum' in schema and value not in schema['enum']:
        raise ContractError(f'{path}: invalid enum {value!r}')
    def matches(t):
        return {'object':isinstance(value,dict), 'array':isinstance(value,list),
                'string':isinstance(value,str), 'boolean':isinstance(value,bool),
                'integer':type(value) is int, 'number':type(value) in (int,float) and math.isfinite(value),
                'null':value is None}[t]
    if 'type' in schema:
        types=schema['type'] if isinstance(schema['type'],list) else [schema['type']]
        if not any(matches(t) for t in types): raise ContractError(f'{path}: wrong type')
    if isinstance(value,dict):
        for key in schema.get('required',[]):
            if key not in value: raise ContractError(f'{path}: missing {key}')
        props=schema.get('properties',{})
        if schema.get('additionalProperties') is False and set(value)-set(props):
            raise ContractError(f'{path}: unknown fields {sorted(set(value)-set(props))}')
        for key,child in value.items():
            if key in props: validate(child,schema=props[key],path=path+'.'+key)
    if isinstance(value,list) and 'items' in schema:
        for i,child in enumerate(value): validate(child,schema=schema['items'],path=f'{path}[{i}]')
    if type(value) in (int,float) and 'minimum' in schema and value < schema['minimum']:
        raise ContractError(f'{path}: below minimum')
    if isinstance(value,str) and 'pattern' in schema and not re.fullmatch(schema['pattern'],value):
        raise ContractError(f'{path}: invalid format')
    return value

def safe_path(root, relative, *, writing=False):
    """Reject every symlink and case alias, not just links escaping the root.
    This constrains trusted mock file operations; it is not an OS sandbox.
    """
    if not isinstance(relative,str) or not relative or '\\' in relative or '\x00' in relative:
        raise ContractError('invalid path')
    p=PurePosixPath(relative)
    if p.is_absolute() or any(x in ('..','.') for x in relative.split('/')) or '//' in relative:
        raise ContractError('path traversal/absolute/non-normalized path')
    root=Path(root).resolve()
    current=root
    for part in p.parts:
        if current.exists():
            aliases=[x.name for x in current.iterdir() if x.name.casefold()==part.casefold()]
            if aliases and aliases != [part]: raise ContractError('case-insensitive collision')
        current=current/part
        if current.is_symlink(): raise ContractError('symlink path prohibited')
    if not current.resolve().is_relative_to(root): raise ContractError('path escape')
    return current

def verify_ref(root, ref):
    validate(ref,'HashRef')
    p=safe_path(root,ref['path'])
    if not p.is_file(): raise ContractError('artifact missing: '+ref['path'])
    raw=p.read_bytes()
    if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:
        raise ContractError('artifact hash/size mismatch: '+ref['path'])
    return p

def file_ref(root, path):
    path=Path(path)
    raw=path.read_bytes()
    return {'path':path.relative_to(Path(root)).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
