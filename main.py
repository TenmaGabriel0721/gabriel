import asyncio
import astrbot.api.star as star
import astrbot.api.event.filter as filter
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.utils.command_parser import CommandParserMixin
from astrbot.core.star.star_handler import star_handlers_registry, StarHandlerMetadata
from astrbot.core.star.star import star_map
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter, PermissionType
from astrbot.api import sp, logger
from astrbot.core.config import AstrBotConfig
from typing import Any, Callable, Dict, List, Optional, Tuple

from .webui import WebUIServer as PermissionWebUIServer


class PermissionManagerCommands(CommandParserMixin):
    """批量权限管理命令类"""

    def __init__(self, context: star.Context):
        self.context = context

    def _get_all_commands_by_plugin(self) -> Dict[str, List[Tuple[StarHandlerMetadata, str, str, bool]]]:
        """
        获取所有插件及其命令列表
        返回: {插件名: [(handler, 命令名, 命令类型, 是否是指令组), ...]}
        """
        plugin_commands = {}
        
        for handler in star_handlers_registry:
            assert isinstance(handler, StarHandlerMetadata)
            if handler.handler_module_path not in star_map:
                continue
            
            plugin = star_map[handler.handler_module_path]
            if not plugin.activated:
                continue
            
            if plugin.name not in plugin_commands:
                plugin_commands[plugin.name] = []
            
            # 检查命令过滤器
            for event_filter in handler.event_filters:
                if isinstance(event_filter, CommandFilter):
                    plugin_commands[plugin.name].append(
                        (handler, event_filter.command_name, "command", False)
                    )
                    break
                elif isinstance(event_filter, CommandGroupFilter):
                    plugin_commands[plugin.name].append(
                        (handler, event_filter.group_name, "command_group", True)
                    )
                    break
        
        return plugin_commands

    async def _get_command_permission(self, plugin_name: str, handler_name: str) -> Optional[str]:
        """获取命令的当前权限配置"""
        alter_cmd_cfg = await sp.global_get("alter_cmd", {})
        plugin_cfg = alter_cmd_cfg.get(plugin_name, {})
        cmd_cfg = plugin_cfg.get(handler_name, {})
        return cmd_cfg.get("permission")
    
    async def _get_command_aliases(self, plugin_name: str, handler_name: str) -> List[str]:
        """获取命令的别名列表"""
        alter_cmd_cfg = await sp.global_get("alter_cmd", {})
        plugin_cfg = alter_cmd_cfg.get(plugin_name, {})
        cmd_cfg = plugin_cfg.get(handler_name, {})
        aliases = cmd_cfg.get("aliases", [])
        # 确保返回的是列表
        if aliases is None:
            return []
        if not isinstance(aliases, list):
            return list(aliases) if aliases else []
        return aliases
    
    async def _set_command_aliases(
        self,
        plugin_name: str,
        handler_name: str,
        aliases: List[str],
        handler: Optional[StarHandlerMetadata] = None
    ):
        """设置命令别名"""
        alter_cmd_cfg = await sp.global_get("alter_cmd", {})
        plugin_cfg = alter_cmd_cfg.get(plugin_name, {})
        cmd_cfg = plugin_cfg.get(handler_name, {})
        cmd_cfg["aliases"] = aliases
        plugin_cfg[handler_name] = cmd_cfg
        alter_cmd_cfg[plugin_name] = plugin_cfg
        await sp.global_put("alter_cmd", alter_cmd_cfg)
        
        # 如果提供了handler，立即更新过滤器
        if handler:
            for event_filter in handler.event_filters:
                if isinstance(event_filter, CommandFilter):
                    # 更新别名集合
                    event_filter.alias = set(aliases)
                    # 清除缓存，强制重新计算完整命令名
                    event_filter._cmpl_cmd_names = None
                    break
                elif isinstance(event_filter, CommandGroupFilter):
                    # 更新别名集合
                    event_filter.alias = set(aliases)
                    # 清除缓存
                    event_filter._cmpl_cmd_names = None
                    break
    
    async def _set_command_name(
        self,
        plugin_name: str,
        handler_name: str,
        new_name: str,
        handler: Optional[StarHandlerMetadata] = None
    ):
        """设置命令名（或指令组名）"""
        alter_cmd_cfg = await sp.global_get("alter_cmd", {})
        plugin_cfg = alter_cmd_cfg.get(plugin_name, {})
        cmd_cfg = plugin_cfg.get(handler_name, {})
        cmd_cfg["name"] = new_name
        plugin_cfg[handler_name] = cmd_cfg
        alter_cmd_cfg[plugin_name] = plugin_cfg
        await sp.global_put("alter_cmd", alter_cmd_cfg)
        
        # 如果提供了handler，立即更新过滤器
        if handler:
            for event_filter in handler.event_filters:
                if isinstance(event_filter, CommandFilter):
                    # 更新命令名
                    event_filter.command_name = new_name
                    # 清除缓存，强制重新计算完整命令名
                    event_filter._cmpl_cmd_names = None
                    break
                elif isinstance(event_filter, CommandGroupFilter):
                    # 更新指令组名
                    event_filter.group_name = new_name
                    # 清除缓存
                    event_filter._cmpl_cmd_names = None
                    break

    async def _set_command_permission(
        self, 
        plugin_name: str, 
        handler_name: str, 
        permission: str,
        handler: Optional[StarHandlerMetadata] = None
    ):
        """设置命令权限"""
        alter_cmd_cfg = await sp.global_get("alter_cmd", {})
        plugin_cfg = alter_cmd_cfg.get(plugin_name, {})
        cmd_cfg = plugin_cfg.get(handler_name, {})
        cmd_cfg["permission"] = permission
        plugin_cfg[handler_name] = cmd_cfg
        alter_cmd_cfg[plugin_name] = plugin_cfg
        await sp.global_put("alter_cmd", alter_cmd_cfg)
        
        # 如果提供了handler，立即更新过滤器
        if handler:
            found_permission_filter = False
            for event_filter in handler.event_filters:
                if isinstance(event_filter, PermissionTypeFilter):
                    if permission == "admin":
                        event_filter.permission_type = PermissionType.ADMIN
                    else:
                        event_filter.permission_type = PermissionType.MEMBER
                    found_permission_filter = True
                    break
            
            if not found_permission_filter:
                handler.event_filters.append(
                    PermissionTypeFilter(
                        PermissionType.ADMIN if permission == "admin" else PermissionType.MEMBER
                    )
                )

    async def _batch_set_plugin_permission(
        self, 
        plugin_name: str, 
        permission: str,
        command_type: Optional[str] = None
    ) -> Tuple[int, int]:
        """
        批量设置插件所有命令的权限
        返回: (成功数量, 总数量)
        """
        plugin_commands = self._get_all_commands_by_plugin()
        
        if plugin_name not in plugin_commands:
            return (0, 0)
        
        success_count = 0
        total_count = 0
        
        for handler, cmd_name, cmd_type, is_group in plugin_commands[plugin_name]:
            # 如果指定了命令类型，只处理该类型
            if command_type and cmd_type != command_type:
                continue
            
            total_count += 1
            await self._set_command_permission(
                plugin_name, 
                handler.handler_name, 
                permission,
                handler
            )
            success_count += 1
        
        return (success_count, total_count)

    async def list_plugins(self, event: AstrMessageEvent):
        """列出所有插件及其命令数量"""
        plugin_commands = self._get_all_commands_by_plugin()
        
        if not plugin_commands:
            await event.send(MessageChain().message("没有找到任何已启用的插件。"))
            return
        
        msg = "📋 已启用插件列表：\n\n"
        for plugin_name, commands in sorted(plugin_commands.items()):
            command_count = len([c for c in commands if c[2] == "command"])
            group_count = len([c for c in commands if c[3]])
            msg += f"🔹 {plugin_name}\n"
            msg += f"   命令数: {command_count}, 指令组数: {group_count}\n"
            msg += f"   使用 /perm plugin {plugin_name} 查看详细命令列表\n\n"
        
        msg += "💡 提示：\n"
        msg += "/perm plugin <插件名> - 查看插件所有命令\n"
        msg += "/perm set plugin <插件名> <admin/member> - 批量设置插件所有命令权限\n"
        msg += "/perm set command <插件名> <命令名> <admin/member> - 设置单个命令权限\n"
        
        await event.send(MessageChain().message(msg))

    async def list_plugin_commands(self, event: AstrMessageEvent, plugin_name: str = ""):
        """列出指定插件的所有命令"""
        if not plugin_name:
            await event.send(MessageChain().message(
                "格式: /perm plugin <插件名>\n"
                "列出指定插件的所有命令及其权限状态。"
            ))
            return
        
        plugin_commands = self._get_all_commands_by_plugin()
        
        if plugin_name not in plugin_commands:
            await event.send(MessageChain().message(f"未找到插件: {plugin_name}"))
            return
        
        commands = plugin_commands[plugin_name]
        alter_cmd_cfg = await sp.global_get("alter_cmd", {})
        plugin_cfg = alter_cmd_cfg.get(plugin_name, {})
        
        msg = f"📋 插件 {plugin_name} 的命令列表：\n\n"
        
        # 按类型分组
        command_list = []
        group_list = []
        
        for handler, cmd_name, cmd_type, is_group in commands:
            current_perm = plugin_cfg.get(handler.handler_name, {}).get("permission", "未设置")
            if current_perm == "未设置":
                # 检查handler中是否有权限过滤器
                for event_filter in handler.event_filters:
                    if isinstance(event_filter, PermissionTypeFilter):
                        if event_filter.permission_type == PermissionType.ADMIN:
                            current_perm = "admin (代码中设置)"
                        else:
                            current_perm = "member (代码中设置)"
                        break
            
            # 获取别名信息
            aliases = plugin_cfg.get(handler.handler_name, {}).get("aliases", [])
            # 如果配置中没有别名，尝试从过滤器中获取
            if not aliases:
                for event_filter in handler.event_filters:
                    if isinstance(event_filter, (CommandFilter, CommandGroupFilter)):
                        if event_filter.alias:
                            aliases = list(event_filter.alias)
                        break
            
            info = {
                "name": cmd_name,
                "type": cmd_type,
                "handler": handler.handler_name,
                "permission": current_perm,
                "aliases": aliases,
                "is_group": is_group
            }
            
            if is_group:
                group_list.append(info)
            else:
                command_list.append(info)
        
        if command_list:
            msg += "📌 命令：\n"
            for cmd in sorted(command_list, key=lambda x: x["name"]):
                perm_icon = "🔒" if cmd["permission"] == "admin" or "admin" in str(cmd["permission"]) else "🔓"
                alias_str = ""
                if cmd.get("aliases"):
                    alias_str = f" (别名: {', '.join(cmd['aliases'])})"
                msg += f"  {perm_icon} {cmd['name']}{alias_str} - 权限: {cmd['permission']}\n"
            msg += "\n"
        
        if group_list:
            msg += "📁 指令组：\n"
            for group in sorted(group_list, key=lambda x: x["name"]):
                perm_icon = "🔒" if group["permission"] == "admin" or "admin" in str(group["permission"]) else "🔓"
                alias_str = ""
                if group.get("aliases"):
                    alias_str = f" (别名: {', '.join(group['aliases'])})"
                msg += f"  {perm_icon} {group['name']}{alias_str} - 权限: {group['permission']}\n"
            msg += "\n"
        
        msg += "💡 提示：\n"
        msg += "/perm set plugin <插件名> <admin/member> - 批量设置所有命令权限\n"
        msg += "/perm set command <插件名> <命令名> <admin/member> - 设置单个命令权限\n"
        msg += "/perm alias add <插件名> <命令名> <别名> - 添加命令别名\n"
        msg += "/perm alias remove <插件名> <命令名> <别名> - 删除命令别名\n"
        msg += "/perm alias list <插件名> <命令名> - 查看命令别名列表\n"
        msg += "/perm name set <插件名> <命令名> <新名称> - 修改命令名或指令组名\n"
        
        await event.send(MessageChain().message(msg))

    async def batch_set_plugin(self, event: AstrMessageEvent, plugin_name: str = "", permission: str = ""):
        """批量设置插件所有命令的权限"""
        if not plugin_name or not permission:
            await event.send(MessageChain().message(
                "格式: /perm set plugin <插件名> <admin/member>\n"
                "批量设置指定插件的所有命令权限。\n\n"
                "示例:\n"
                "/perm set plugin astrbot admin - 将 astrbot 插件的所有命令设为管理员权限\n"
                "/perm set plugin astrbot member - 将 astrbot 插件的所有命令设为成员权限"
            ))
            return
        
        if permission not in ["admin", "member"]:
            await event.send(MessageChain().message("权限类型错误，只能是 admin 或 member"))
            return
        
        plugin_commands = self._get_all_commands_by_plugin()
        if plugin_name not in plugin_commands:
            await event.send(MessageChain().message(f"未找到插件: {plugin_name}"))
            return
        
        success_count, total_count = await self._batch_set_plugin_permission(
            plugin_name, 
            permission
        )
        
        perm_text = "管理员权限" if permission == "admin" else "成员权限"
        await event.send(MessageChain().message(
            f"✅ 成功设置 {plugin_name} 插件的 {success_count}/{total_count} 个命令为 {perm_text}。"
        ))

    async def set_command(self, event: AstrMessageEvent, plugin_name: str = "", command_name: str = "", permission: str = ""):
        """设置单个命令的权限"""
        if not plugin_name or not command_name or not permission:
            await event.send(MessageChain().message(
                "格式: /perm set command <插件名> <命令名> <admin/member>\n"
                "设置指定插件的单个命令权限。\n\n"
                "示例:\n"
                "/perm set command astrbot help admin - 将 astrbot 插件的 help 命令设为管理员权限"
            ))
            return
        
        if permission not in ["admin", "member"]:
            await event.send(MessageChain().message("权限类型错误，只能是 admin 或 member"))
            return
        
        plugin_commands = self._get_all_commands_by_plugin()
        if plugin_name not in plugin_commands:
            await event.send(MessageChain().message(f"未找到插件: {plugin_name}"))
            return
        
        # 查找命令
        found_handler = None
        for handler, cmd_name, cmd_type, is_group in plugin_commands[plugin_name]:
            if cmd_name == command_name:
                found_handler = handler
                break
        
        if not found_handler:
            await event.send(MessageChain().message(f"未找到命令: {command_name}"))
            return
        
        await self._set_command_permission(
            plugin_name,
            found_handler.handler_name,
            permission,
            found_handler
        )
        
        perm_text = "管理员权限" if permission == "admin" else "成员权限"
        await event.send(MessageChain().message(
            f"✅ 成功将 {plugin_name} 插件的命令 {command_name} 设置为 {perm_text}。"
        ))

    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_msg = """🔐 批量权限管理插件帮助

📋 命令列表：

1️⃣ 查看插件列表
   /perm list
   列出所有已启用的插件及其命令数量

2️⃣ 查看插件命令
   /perm plugin <插件名>
   列出指定插件的所有命令及其权限状态

3️⃣ 批量设置插件权限
   /perm set plugin <插件名> <admin/member>
   批量设置指定插件的所有命令权限
   
   示例：
   /perm set plugin astrbot admin
   /perm set plugin astrbot member

4️⃣ 设置单个命令权限
   /perm set command <插件名> <命令名> <admin/member>
   设置指定插件的单个命令权限
   
   示例：
   /perm set command astrbot help admin

5️⃣ 修改命令名或指令组名
   /perm name set <插件名> <命令名> <新名称>
   修改指定命令或指令组的名称
   
   示例：
   /perm name set astrbot help 帮助

6️⃣ 管理命令别名
   /perm alias add <插件名> <命令名> <别名> - 添加别名
   /perm alias remove <插件名> <命令名> <别名> - 删除别名
   /perm alias list <插件名> <命令名> - 查看别名列表
   
   示例：
   /perm alias add astrbot help h
   /perm alias remove astrbot help h
   /perm alias list astrbot help

💡 权限说明：
   - admin: 仅管理员可使用
   - member: 所有成员可使用（管理员也可用）

📝 注意：
   - 批量设置会覆盖所有命令的权限配置
   - 设置后立即生效，无需重启
"""
        await event.send(MessageChain().message(help_msg))
    
    async def set_command_name(self, event: AstrMessageEvent, plugin_name: str = "", command_name: str = "", new_name: str = ""):
        """修改命令名或指令组名"""
        if not plugin_name or not command_name or not new_name:
            await event.send(MessageChain().message(
                "格式: /perm name set <插件名> <命令名> <新名称>\n"
                "修改指定命令或指令组的名称。\n\n"
                "示例:\n"
                "/perm name set astrbot help 帮助 - 将 help 命令改名为 帮助"
            ))
            return
        
        plugin_commands = self._get_all_commands_by_plugin()
        if plugin_name not in plugin_commands:
            await event.send(MessageChain().message(f"未找到插件: {plugin_name}"))
            return
        
        # 查找命令
        found_handler = None
        for handler, cmd_name, cmd_type, is_group in plugin_commands[plugin_name]:
            if cmd_name == command_name:
                found_handler = handler
                break
        
        if not found_handler:
            await event.send(MessageChain().message(f"未找到命令: {command_name}"))
            return
        
        await self._set_command_name(
            plugin_name,
            found_handler.handler_name,
            new_name,
            found_handler
        )
        
        cmd_type_str = "指令组" if found_handler.event_filters and isinstance(found_handler.event_filters[0], CommandGroupFilter) else "命令"
        await event.send(MessageChain().message(
            f"✅ 成功将 {plugin_name} 插件的{cmd_type_str} {command_name} 改名为 {new_name}。"
        ))
    
    async def add_alias(self, event: AstrMessageEvent, plugin_name: str = "", command_name: str = "", alias: str = ""):
        """添加命令别名"""
        if not plugin_name or not command_name or not alias:
            await event.send(MessageChain().message(
                "格式: /perm alias add <插件名> <命令名> <别名>\n"
                "为指定命令添加别名。\n\n"
                "示例:\n"
                "/perm alias add astrbot help h - 为 help 命令添加别名 h"
            ))
            return
        
        plugin_commands = self._get_all_commands_by_plugin()
        if plugin_name not in plugin_commands:
            await event.send(MessageChain().message(f"未找到插件: {plugin_name}"))
            return
        
        # 查找命令
        found_handler = None
        for handler, cmd_name, cmd_type, is_group in plugin_commands[plugin_name]:
            if cmd_name == command_name:
                found_handler = handler
                break
        
        if not found_handler:
            await event.send(MessageChain().message(f"未找到命令: {command_name}"))
            return
        
        # 获取当前别名列表
        current_aliases = await self._get_command_aliases(plugin_name, found_handler.handler_name)
        # 确保 current_aliases 是一个列表
        if not current_aliases:
            current_aliases = []
            # 尝试从过滤器中获取
            for event_filter in found_handler.event_filters:
                if isinstance(event_filter, (CommandFilter, CommandGroupFilter)):
                    if event_filter.alias:
                        current_aliases = list(event_filter.alias)
                        break
        
        # 确保 current_aliases 是一个列表（防止 None）
        if not isinstance(current_aliases, list):
            current_aliases = list(current_aliases) if current_aliases else []
        
        if alias in current_aliases:
            await event.send(MessageChain().message(f"别名 {alias} 已存在"))
            return
        
        current_aliases.append(alias)
        await self._set_command_aliases(
            plugin_name,
            found_handler.handler_name,
            current_aliases,
            found_handler
        )
        
        await event.send(MessageChain().message(
            f"✅ 成功为 {plugin_name} 插件的命令 {command_name} 添加别名 {alias}。"
        ))
    
    async def remove_alias(self, event: AstrMessageEvent, plugin_name: str = "", command_name: str = "", alias: str = ""):
        """删除命令别名"""
        if not plugin_name or not command_name or not alias:
            await event.send(MessageChain().message(
                "格式: /perm alias remove <插件名> <命令名> <别名>\n"
                "删除指定命令的别名。\n\n"
                "示例:\n"
                "/perm alias remove astrbot help h - 删除 help 命令的别名 h"
            ))
            return
        
        plugin_commands = self._get_all_commands_by_plugin()
        if plugin_name not in plugin_commands:
            await event.send(MessageChain().message(f"未找到插件: {plugin_name}"))
            return
        
        # 查找命令
        found_handler = None
        for handler, cmd_name, cmd_type, is_group in plugin_commands[plugin_name]:
            if cmd_name == command_name:
                found_handler = handler
                break
        
        if not found_handler:
            await event.send(MessageChain().message(f"未找到命令: {command_name}"))
            return
        
        # 获取当前别名列表
        current_aliases = await self._get_command_aliases(plugin_name, found_handler.handler_name)
        # 确保 current_aliases 是一个列表
        if not current_aliases:
            current_aliases = []
            # 尝试从过滤器中获取
            for event_filter in found_handler.event_filters:
                if isinstance(event_filter, (CommandFilter, CommandGroupFilter)):
                    if event_filter.alias:
                        current_aliases = list(event_filter.alias)
                        break
        
        # 确保 current_aliases 是一个列表（防止 None）
        if not isinstance(current_aliases, list):
            current_aliases = list(current_aliases) if current_aliases else []
        
        if alias not in current_aliases:
            await event.send(MessageChain().message(f"别名 {alias} 不存在"))
            return
        
        current_aliases.remove(alias)
        await self._set_command_aliases(
            plugin_name,
            found_handler.handler_name,
            current_aliases,
            found_handler
        )
        
        await event.send(MessageChain().message(
            f"✅ 成功删除 {plugin_name} 插件的命令 {command_name} 的别名 {alias}。"
        ))
    
    async def list_aliases(self, event: AstrMessageEvent, plugin_name: str = "", command_name: str = ""):
        """查看命令别名列表"""
        if not plugin_name or not command_name:
            await event.send(MessageChain().message(
                "格式: /perm alias list <插件名> <命令名>\n"
                "查看指定命令的别名列表。\n\n"
                "示例:\n"
                "/perm alias list astrbot help - 查看 help 命令的别名列表"
            ))
            return
        
        plugin_commands = self._get_all_commands_by_plugin()
        if plugin_name not in plugin_commands:
            await event.send(MessageChain().message(f"未找到插件: {plugin_name}"))
            return
        
        # 查找命令
        found_handler = None
        for handler, cmd_name, cmd_type, is_group in plugin_commands[plugin_name]:
            if cmd_name == command_name:
                found_handler = handler
                break
        
        if not found_handler:
            await event.send(MessageChain().message(f"未找到命令: {command_name}"))
            return
        
        # 获取当前别名列表
        aliases = await self._get_command_aliases(plugin_name, found_handler.handler_name)
        # 确保 aliases 是一个列表
        if not aliases:
            aliases = []
            # 尝试从过滤器中获取
            for event_filter in found_handler.event_filters:
                if isinstance(event_filter, (CommandFilter, CommandGroupFilter)):
                    if event_filter.alias:
                        aliases = list(event_filter.alias)
                        break
        
        # 确保 aliases 是一个列表（防止 None）
        if not isinstance(aliases, list):
            aliases = list(aliases) if aliases else []
        
        if not aliases:
            await event.send(MessageChain().message(
                f"命令 {command_name} 没有设置别名。"
            ))
        else:
            await event.send(MessageChain().message(
                f"命令 {command_name} 的别名列表：\n" + "\n".join([f"  - {alias}" for alias in aliases])
            ))


class Main(star.Star):
    """批量权限管理插件 - 提供便捷的批量权限设置功能"""

    def __init__(self, context: star.Context, config: AstrBotConfig = None) -> None:
        self.context = context
        self.config = config or {}
        
        # 从配置中读取设置
        webui_config = self.config.get("webui", {}) if self.config else {}
        self.webui_enabled = webui_config.get("enabled", True) if webui_config else True
        self.webui_secret_key = webui_config.get("secret_key", "PermissionManager") if webui_config else "PermissionManager"
        self.webui_port = webui_config.get("port", 8888) if webui_config else 8888
        self.webui_host = webui_config.get("host", "0.0.0.0") if webui_config else "0.0.0.0"
        
        self.command_enabled = self.config.get("command_enabled", True) if self.config else True
        self.default_permission = self.config.get("default_permission", "member") if self.config else "member"
        self.auto_apply_on_load = self.config.get("auto_apply_on_load", True) if self.config else True
        self.show_permission_in_help = self.config.get("show_permission_in_help", True) if self.config else True
        self.batch_operation_confirm = self.config.get("batch_operation_confirm", True) if self.config else True
        self.log_permission_changes = self.config.get("log_permission_changes", False) if self.config else False
        
        self.perm_cmd = PermissionManagerCommands(context)
        self.webui_server: PermissionWebUIServer | None = None
        self._monitor_task: Optional[asyncio.Task] = None
        
        if self.log_permission_changes:
            logger.info(f"权限管理插件已加载 - Web UI: {self.webui_enabled} (端口: {self.webui_port}), 命令行: {self.command_enabled}")
    
    async def initialize(self):
        """插件初始化方法，在插件加载后自动调用"""
        # 如果启用了自动应用配置，从 alter_cmd 配置中加载并应用到所有 handler
        if self.auto_apply_on_load:
            await self._apply_config_to_handlers()
            # 启动后台监控任务，定期检查并应用配置，确保插件重载后配置仍然生效
            self._monitor_task = asyncio.create_task(self._monitor_and_apply_config())
        
        # 如果 Web UI 已启用，自动启动
        if self.webui_enabled:
            # 使用 asyncio.create_task 在后台启动 Web UI
            asyncio.create_task(self._auto_start_webui())
    
    async def _apply_config_to_handlers(self):
        """从 alter_cmd 配置中加载并应用到所有 handler 的过滤器"""
        try:
            alter_cmd_cfg = await sp.global_get("alter_cmd", {})
            if not alter_cmd_cfg:
                return
            
            applied_count = 0
            
            # 遍历所有已注册的 handler
            for handler in star_handlers_registry:
                assert isinstance(handler, StarHandlerMetadata)
                if handler.handler_module_path not in star_map:
                    continue
                
                plugin = star_map[handler.handler_module_path]
                if not plugin.activated:
                    continue
                
                plugin_name = plugin.name
                handler_name = handler.handler_name
                
                # 获取该插件的配置
                plugin_cfg = alter_cmd_cfg.get(plugin_name, {})
                cmd_cfg = plugin_cfg.get(handler_name, {})
                
                if not cmd_cfg:
                    continue
                
                # 查找命令过滤器或指令组过滤器
                command_filter = None
                command_group_filter = None
                for event_filter in handler.event_filters:
                    if isinstance(event_filter, CommandFilter):
                        command_filter = event_filter
                        break
                    elif isinstance(event_filter, CommandGroupFilter):
                        command_group_filter = event_filter
                        break
                
                if not command_filter and not command_group_filter:
                    continue
                
                # 应用命令名/指令组名
                if "name" in cmd_cfg:
                    new_name = cmd_cfg["name"]
                    if command_filter:
                        command_filter.command_name = new_name
                        command_filter._cmpl_cmd_names = None  # 清除缓存
                    elif command_group_filter:
                        command_group_filter.group_name = new_name
                        command_group_filter._cmpl_cmd_names = None  # 清除缓存
                
                # 应用别名
                if "aliases" in cmd_cfg:
                    aliases = cmd_cfg["aliases"]
                    # 确保 aliases 是列表类型
                    if aliases is None:
                        aliases = []
                    elif not isinstance(aliases, list):
                        aliases = list(aliases) if aliases else []
                    
                    if command_filter:
                        command_filter.alias = set(aliases)
                        command_filter._cmpl_cmd_names = None  # 清除缓存
                    elif command_group_filter:
                        command_group_filter.alias = set(aliases)
                        command_group_filter._cmpl_cmd_names = None  # 清除缓存
                
                # 应用权限（虽然框架可能会自动应用，但为了确保一致性，我们也应用一下）
                if "permission" in cmd_cfg:
                    permission = cmd_cfg["permission"]
                    if permission in ["admin", "member"]:
                        found_permission_filter = False
                        for event_filter in handler.event_filters:
                            if isinstance(event_filter, PermissionTypeFilter):
                                if permission == "admin":
                                    event_filter.permission_type = PermissionType.ADMIN
                                else:
                                    event_filter.permission_type = PermissionType.MEMBER
                                found_permission_filter = True
                                break
                        
                        if not found_permission_filter:
                            handler.event_filters.append(
                                PermissionTypeFilter(
                                    PermissionType.ADMIN if permission == "admin" else PermissionType.MEMBER
                                )
                            )
                
                applied_count += 1
            
            if self.log_permission_changes and applied_count > 0:
                logger.info(f"已从配置中加载并应用到 {applied_count} 个命令处理器")
        
        except Exception as e:
            logger.error(f"加载 alter_cmd 配置时出错: {e}", exc_info=True)
    
    async def _monitor_and_apply_config(self):
        """后台监控任务，定期检查并应用配置，确保插件重载后配置仍然生效"""
        # 记录已处理的 handler 标识（插件名+handler名），用于检测是否有新的 handler 注册
        last_handler_signatures = set()
        check_interval = 2  # 检查间隔（秒）
        apply_interval = 30  # 定期应用配置间隔（秒）
        last_full_apply = 0
        
        import time
        
        while True:
            try:
                await asyncio.sleep(check_interval)
                current_time = time.time()
                
                # 获取当前所有 handler 的签名（插件名:handler名）
                current_handler_signatures = set()
                for handler in star_handlers_registry:
                    assert isinstance(handler, StarHandlerMetadata)
                    if handler.handler_module_path not in star_map:
                        continue
                    plugin = star_map[handler.handler_module_path]
                    if not plugin.activated:
                        continue
                    signature = f"{plugin.name}:{handler.handler_name}"
                    current_handler_signatures.add(signature)
                
                # 如果 handler 集合发生变化，或者达到定期应用时间，重新应用配置
                should_apply = False
                
                # 检查是否有新的 handler（handler 签名不在上次记录中）
                if current_handler_signatures != last_handler_signatures:
                    new_handlers = current_handler_signatures - last_handler_signatures
                    removed_handlers = last_handler_signatures - current_handler_signatures
                    if new_handlers or removed_handlers:
                        should_apply = True
                        if self.log_permission_changes:
                            if new_handlers:
                                logger.debug(f"检测到 {len(new_handlers)} 个新注册的 handler，将重新应用配置")
                            if removed_handlers:
                                logger.debug(f"检测到 {len(removed_handlers)} 个 handler 被移除（可能正在重载），将重新应用配置")
                        # 等待一小段时间，确保插件重载完成
                        await asyncio.sleep(1)
                
                # 定期重新应用配置（即使 handler 没有变化，也要确保配置生效）
                if current_time - last_full_apply >= apply_interval:
                    should_apply = True
                    last_full_apply = current_time
                
                if should_apply and self.auto_apply_on_load:
                    await self._apply_config_to_handlers()
                
                # 更新记录的 handler 签名集合
                last_handler_signatures = current_handler_signatures
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控配置应用任务出错: {e}", exc_info=True)
                await asyncio.sleep(5)  # 出错后等待更长时间再重试

    @filter.command_group("perm")
    def perm(self):
        """权限管理命令组"""
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @perm.command("list")
    async def perm_list(self, event: AstrMessageEvent):
        """列出所有插件"""
        if not self.command_enabled:
            await event.send(MessageChain().message("命令行功能已禁用，请在 Web UI 中管理权限。"))
            return
        await self.perm_cmd.list_plugins(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @perm.command("plugin")
    async def perm_plugin(self, event: AstrMessageEvent, plugin_name: str = ""):
        """查看插件命令列表"""
        if not self.command_enabled:
            await event.send(MessageChain().message("命令行功能已禁用，请在 Web UI 中管理权限。"))
            return
        await self.perm_cmd.list_plugin_commands(event, plugin_name)

    @perm.group("set")
    def perm_set(self):
        """设置权限命令组"""
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @perm_set.command("plugin")
    async def perm_set_plugin(self, event: AstrMessageEvent, plugin_name: str = "", permission: str = ""):
        """批量设置插件权限"""
        if not self.command_enabled:
            await event.send(MessageChain().message("命令行功能已禁用，请在 Web UI 中管理权限。"))
            return
        
        # 如果需要确认
        if self.batch_operation_confirm:
            # 这里可以添加确认逻辑，暂时直接执行
            pass
        
        await self.perm_cmd.batch_set_plugin(event, plugin_name, permission)
        
        if self.log_permission_changes:
            logger.info(f"批量设置插件 {plugin_name} 的权限为 {permission}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @perm_set.command("command")
    async def perm_set_command(self, event: AstrMessageEvent, plugin_name: str = "", command_name: str = "", permission: str = ""):
        """设置单个命令权限"""
        if not self.command_enabled:
            await event.send(MessageChain().message("命令行功能已禁用，请在 Web UI 中管理权限。"))
            return
        
        await self.perm_cmd.set_command(event, plugin_name, command_name, permission)
        
        if self.log_permission_changes:
            logger.info(f"设置插件 {plugin_name} 的命令 {command_name} 的权限为 {permission}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @perm.command("help")
    async def perm_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        if not self.command_enabled:
            await event.send(MessageChain().message("命令行功能已禁用，请在 Web UI 中管理权限。"))
            return
        await self.perm_cmd.show_help(event)
    
    @perm.group("name")
    def perm_name(self):
        """修改命令名命令组"""
        pass
    
    @filter.permission_type(filter.PermissionType.ADMIN)
    @perm_name.command("set")
    async def perm_name_set(self, event: AstrMessageEvent, plugin_name: str = "", command_name: str = "", new_name: str = ""):
        """修改命令名或指令组名"""
        if not self.command_enabled:
            await event.send(MessageChain().message("命令行功能已禁用，请在 Web UI 中管理权限。"))
            return
        await self.perm_cmd.set_command_name(event, plugin_name, command_name, new_name)
    
    @perm.group("alias")
    def perm_alias(self):
        """管理别名命令组"""
        pass
    
    @filter.permission_type(filter.PermissionType.ADMIN)
    @perm_alias.command("add")
    async def perm_alias_add(self, event: AstrMessageEvent, plugin_name: str = "", command_name: str = "", alias: str = ""):
        """添加命令别名"""
        if not self.command_enabled:
            await event.send(MessageChain().message("命令行功能已禁用，请在 Web UI 中管理权限。"))
            return
        await self.perm_cmd.add_alias(event, plugin_name, command_name, alias)
    
    @filter.permission_type(filter.PermissionType.ADMIN)
    @perm_alias.command("remove")
    async def perm_alias_remove(self, event: AstrMessageEvent, plugin_name: str = "", command_name: str = "", alias: str = ""):
        """删除命令别名"""
        if not self.command_enabled:
            await event.send(MessageChain().message("命令行功能已禁用，请在 Web UI 中管理权限。"))
            return
        await self.perm_cmd.remove_alias(event, plugin_name, command_name, alias)
    
    @filter.permission_type(filter.PermissionType.ADMIN)
    @perm_alias.command("list")
    async def perm_alias_list(self, event: AstrMessageEvent, plugin_name: str = "", command_name: str = ""):
        """查看命令别名列表"""
        if not self.command_enabled:
            await event.send(MessageChain().message("命令行功能已禁用，请在 Web UI 中管理权限。"))
            return
        await self.perm_cmd.list_aliases(event, plugin_name, command_name)
    
    @filter.permission_type(filter.PermissionType.ADMIN)
    @perm.command("webui")
    async def perm_webui(self, event: AstrMessageEvent, action: str = ""):
        """启动/停止 Web UI"""
        if not self.webui_enabled:
            await event.send(MessageChain().message("Web UI 功能已禁用，请在插件配置中启用。"))
            return
        
        if action == "start":
            await self._start_webui(event)
        elif action == "stop":
            await self._stop_webui(event)
        elif action == "status":
            await self._webui_status(event)
        else:
            await event.send(MessageChain().message(
                "Web UI 管理命令：\n"
                "/perm webui start - 启动 Web UI\n"
                "/perm webui stop - 停止 Web UI\n"
                "/perm webui status - 查看 Web UI 状态\n\n"
                f"当前配置：端口 {self.webui_port}，主机 {self.webui_host}"
            ))
    
    async def _auto_start_webui(self):
        """自动启动 Web UI（静默启动，不发送消息）"""
        if not self.webui_enabled:
            return

        server = self._ensure_webui_server()
        if server.is_running:
            logger.info("Web UI 已经在运行中")
            return

        logger.info(f"正在自动启动权限管理 Web UI (端口: {self.webui_port})...")

        if not await self._is_port_available():
            logger.warning(f"端口 {self.webui_port} 已被占用，Web UI 启动失败。请更换端口后重试。")
            return

        try:
            await server.start()
            logger.info(
                "✅ 权限管理 Web UI 已自动启动！\n"
                "🔗 访问地址: http://%s:%s/admin\n"
                "🔑 密钥请到插件配置文件中查看（webui.secret_key）",
                self._get_webui_display_host(),
                self.webui_port,
            )
        except Exception as e:
            logger.error(f"自动启动 Web UI 失败: {e}", exc_info=True)

    async def _start_webui(self, event: AstrMessageEvent = None):
        """启动 Web UI（手动启动，会发送消息）"""
        server = self._ensure_webui_server()

        if server.is_running:
            if event:
                await event.send(MessageChain().message("❌ Web UI 已经在运行中"))
            return

        if event:
            await event.send(MessageChain().message("🔄 正在启动权限管理 Web UI..."))

        if not await self._is_port_available():
            if event:
                await event.send(
                    MessageChain().message(f"❌ 端口 {self.webui_port} 已被占用，请更换端口后重试")
                )
            else:
                logger.warning(
                    f"端口 {self.webui_port} 已被占用，无法启动权限管理 Web UI"
                )
            return

        try:
            await server.start()
            if event:
                display_host = self._get_webui_display_host()
                message = (
                    f"✅ 权限管理 Web UI 已启动！\n"
                    f"🔗 请访问 http://{display_host}:{self.webui_port}/admin\n"
                    f"🔑 密钥请到插件配置文件中查看（webui.secret_key）\n\n"
                    f"⚠️ 重要提示：\n"
                    f"• 如需公网访问，请自行配置端口转发和防火墙规则\n"
                    f"• 确保端口 {self.webui_port} 已开放并映射到公网IP\n"
                    f"• 建议使用反向代理（如Nginx）增强安全性\n"
                    f"• 请妥善保管密钥，不要泄露给他人"
                )
                await event.send(MessageChain().message(message))
        except Exception as e:
            logger.error(f"启动 Web UI 失败: {e}", exc_info=True)
            if event:
                await event.send(MessageChain().message(f"❌ 启动 Web UI 失败: {e}"))

    async def _stop_webui(self, event: AstrMessageEvent):
        """停止 Web UI"""
        server = self.webui_server
        if not server or not server.is_running:
            await event.send(MessageChain().message("❌ Web UI 没有在运行中"))
            return

        try:
            await server.stop()
            await event.send(MessageChain().message("✅ Web UI 已关闭"))
        except Exception as e:
            logger.error(f"关闭 Web UI 失败: {e}", exc_info=True)
            await event.send(MessageChain().message(f"❌ 关闭 Web UI 失败: {e}"))

    async def _webui_status(self, event: AstrMessageEvent):
        """查看 Web UI 状态"""
        server = self.webui_server
        is_running = server.is_running if server else False
        status = "运行中" if is_running else "未运行"

        display_host = self._get_webui_display_host()

        await event.send(
            MessageChain().message(
                f"Web UI 状态：{status}\n"
                f"端口：{self.webui_port}\n"
                f"主机：{self.webui_host}\n"
                f"访问地址：http://{display_host}:{self.webui_port}/admin\n"
                f"密钥：请到插件配置文件中查看（webui.secret_key）"
            )
        )

    def _ensure_webui_server(self) -> PermissionWebUIServer:
        if self.webui_server is None:
            app_factory = self._get_webui_app_factory()
            self.webui_server = PermissionWebUIServer(
                host=self.webui_host,
                port=self.webui_port,
                app_factory=app_factory,
                startup_path="/admin",
            )
        return self.webui_server

    def _get_webui_app_factory(self) -> Callable[[], Any]:
        from .manager.server import create_app
        from .manager.service import PermissionService

        secret_key = self.webui_secret_key

        def _factory():
            services = {"permission_service": PermissionService()}
            return create_app(secret_key=secret_key, services=services)

        return _factory

    def _get_webui_display_host(self) -> str:
        return "127.0.0.1" if self.webui_host in ("0.0.0.0", "") else self.webui_host

    async def _is_port_available(self) -> bool:
        import socket

        def check() -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    bind_host = self.webui_host or "0.0.0.0"
                    sock.bind((bind_host, self.webui_port))
                except OSError:
                    return False
                return True

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, check)
    
    async def terminate(self):
        """插件被卸载/停用时调用"""
        # 停止监控任务
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"停止监控任务时出错: {e}", exc_info=True)
            self._monitor_task = None
        
        # 停止 Web UI 服务
        if self.webui_server and self.webui_server.is_running:
            try:
                await self.webui_server.stop()
            except Exception as e:
                logger.error(f"停止 Web UI 服务时出错: {e}", exc_info=True)
        self.webui_server = None
        logger.info("权限管理插件已成功终止。")

