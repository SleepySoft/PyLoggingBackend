import os
import sys
import logging
from typing import List, Dict, Any


self_path = os.path.dirname(os.path.abspath(__file__))


def get_logger_module_file_path(logger_name):
    module = sys.modules.get(logger_name)
    if module and hasattr(module, '__file__'):
        return module.__file__
    return None


class LoggerManager:
    """Logging manager for dynamically managing logging configurations"""

    def __init__(self):
        self.loggers = {}
        self.disabled_level = 100  # Custom disabled level, higher than CRITICAL

    def get_all_loggers(self) -> List[Dict[str, Any]]:
        """Get information for all loggers"""
        loggers_info = []
        project_root = ''

        # Get root logger
        root_logger = logging.getLogger()
        loggers_info.append({
            'name': 'root',
            'path': "",
            'level': self._get_level_name(root_logger.level),
            'effective_level': self._get_level_name(root_logger.getEffectiveLevel()),
            'disabled': root_logger.disabled,
            'in_project': True,
            'handlers_count': len(root_logger.handlers)
        })

        # Get all created loggers
        for name, logger in logging.Logger.manager.loggerDict.items():
            if isinstance(logger, logging.Logger):
                module_path = get_logger_module_file_path(name)
                if name == '__main__':
                    project_root = os.path.dirname(module_path)
                loggers_info.append({
                    'name': name,
                    'path': module_path,
                    'level': self._get_level_name(logger.level),
                    'effective_level': self._get_level_name(logger.getEffectiveLevel()),
                    'disabled': logger.disabled,
                    'in_project': False,
                    'handlers_count': len(logger.handlers)
                })
                self.loggers[name] = logger

        if project_root:
            for i, logger in enumerate(loggers_info):
                if i == 0:
                    loggers_info[0]['path'] = project_root
                else:
                    module_in_project = self._is_module_in_project(loggers_info[i]['path'], project_root)
                    loggers_info[i]['in_project'] = module_in_project

        return sorted(loggers_info, key=lambda x: x['name'])

    def set_logger_level(self, logger_name: str, level: str, enabled: bool) -> bool:
        """Set logger level and enabled status"""
        try:
            if logger_name == 'root':
                logger = logging.getLogger()
            else:
                logger = logging.getLogger(logger_name)

            if not enabled:
                logger.disabled = True
                return True

            logger.disabled = False
            level_mapping = {
                'NOTSET': logging.NOTSET,
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
                'CRITICAL': logging.CRITICAL
            }

            if level in level_mapping:
                logger.setLevel(level_mapping[level])
                return True
            else:
                return False

        except Exception as e:
            logging.error(f"Failed to set logger level: {e}")
            return False

    def _get_level_name(self, level: int) -> str:
        """Convert level number to name"""
        if level == self.disabled_level:
            return 'DISABLED'
        return logging.getLevelName(level) if logging.getLevelName(level) != 'Level %s' % level else str(level)

    def _is_module_in_project(self, module_path: str, project_root: str) -> bool:
        """判断模块是否属于当前工程"""
        if not module_path or not os.path.exists(module_path):
            return False

        try:
            # 规范化路径
            abs_module_path = os.path.normpath(os.path.abspath(module_path))
            abs_project_root = os.path.normpath(os.path.abspath(project_root))

            # 使用commonprefix方法更准确判断路径关系
            common_path = os.path.commonpath([abs_module_path, abs_project_root])
            return common_path == abs_project_root
        except (ValueError, OSError):
            # 处理路径比较中的异常情况
            return module_path.startswith(project_root)
