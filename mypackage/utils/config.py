import os
import importlib
from typing import List,Tuple,Generator

__all__ = [
    'get_pkg_root_path', 'get_pkg_arch_path',
    'discover_archs', 'get_arch_pkg', 'get_arch_cls'
]

__ROOT_PATH__ = os.path.sep.join(os.path.realpath(__file__).split(os.path.sep)[:-2])

def get_pkg_root_path() -> str:
    global __ROOT_PATH__
    return __ROOT_PATH__

def get_pkg_arch_path() -> str:
    root_path = get_pkg_root_path()
    return os.path.join(root_path,"arch")

def discover_archs() -> Generator:
    """yields tuple as architecture name and full path of the module

    Yields:
        Generator: (architecture name, full path of the module)
    """

    arch_path = get_pkg_arch_path()
    for candidate in os.listdir(arch_path):
        file_path = os.path.join(arch_path,candidate)
        if os.path.isfile(file_path) or candidate=='__pycache__': continue
        module_path = os.path.join(file_path,"module.py")
        assert os.path.isfile(module_path),f"cannot find: {module_path}. {candidate} must contain module.py"
        yield (candidate,module_path)

def get_arch_pkg(arch:str):
    arch_path = get_pkg_arch_path()
    for arch_name,module_path in discover_archs():
        if arch_name != arch: continue
        abs_m_p = module_path.replace(arch_path,'',1).replace(".py", '',-1)
        abs_m_p = abs_m_p.replace(os.path.sep,"",1) if abs_m_p.startswith(os.path.sep) else abs_m_p
        abs_m_p = abs_m_p.replace(os.path.sep,".")
        return importlib.import_module(f"mypackage.arch.{abs_m_p}")

    raise AssertionError(f"given {arch} is not found")

def get_arch_cls(arch:str):
    arch_path = get_pkg_arch_path()
    for arch_name,module_path in discover_archs():
        if arch_name != arch: continue
        abs_m_p = module_path.replace(arch_path,'',1).replace(".py", '',-1)
        abs_m_p = abs_m_p.replace(os.path.sep,"",1) if abs_m_p.startswith(os.path.sep) else abs_m_p
        abs_m_p = abs_m_p.replace(os.path.sep,".")
        api = importlib.import_module(f"mypackage.arch.{abs_m_p}")

        for d in dir(api):
            if d.lower() != arch: continue
            return getattr(api,d)

    raise AssertionError(f"given {arch} nn.Module is not found. Hint: arch folder may contain broken architecture implementation.")