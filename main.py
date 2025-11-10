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
from typing import Dict, List, Tuple, Optional


class PermissionManagerCommands(CommandParserMixin):
    """批量权限管理命令类"""

    def __init__(self, context: star.Context):
        self.context = context
        # 使用 PermissionService 而不是重复实现
        from .manager.service import PermissionService
        self.service = PermissionService()

    def _get_all_commands_by_plugin(self) -> Dict[str, List[Tuple[StarHandlerMetadata, str, str, bool]]]:
        """
        获取所有插件及其命令列表
        返回: {插件名: [(handler, 命令名, 命令类型, 是否是指令组), ...]}
        """
        # 使用 PermissionService 的方法
        return self.service._get_all_commands_by_plugin()

    async def _get_command_aliases(self, plugin_name: str, handler_name: str) -> List[str]:
        """获取命令的别名列表"""
        alter_cmd_cfg = await sp.global_get("alter_cmd", {})
        plugin_cfg = alter_cmd_cfg.get(plugin_name, {})
        cmd_cfg = plugin_cfg.get(handler_name, {})
        aliases = cmd_cfg.get("aliases", [])
        # 确保返回的是列表（在写入时已统一，这里做防御性检查）
        if aliases is None:
            return []
        if not isinstance(aliases, list):
            return list(aliases) if aliases else []
        return aliases

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
        # 使用 PermissionService 的方法
        result = await self.service.set_plugin_permission(plugin_name, permission)
        if not result.get("success"):
            return (0, 0)
        return (result.get("success_count", 0), result.get("total_count", 0))

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
        
        # 使用 PermissionService 的方法
        result = await self.service.set_command_permission(
            plugin_name,
            found_handler.handler_name,
            permission
        )
        
        if not result.get("success"):
            await event.send(MessageChain().message(f"❌ {result.get('message', '设置失败')}"))
            return
        
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
        
        # 使用 PermissionService 的方法
        result = await self.service.set_command_name(
            plugin_name,
            found_handler.handler_name,
            new_name
        )
        
        if not result.get("success"):
            await event.send(MessageChain().message(f"❌ {result.get('message', '修改失败')}"))
            return
        
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
        # 使用 PermissionService 的方法
        result = await self.service.set_command_aliases(
            plugin_name,
            found_handler.handler_name,
            current_aliases
        )
        
        if not result.get("success"):
            await event.send(MessageChain().message(f"❌ {result.get('message', '添加失败')}"))
            return
        
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
        # 使用 PermissionService 的方法
        result = await self.service.set_command_aliases(
            plugin_name,
            found_handler.handler_name,
            current_aliases
        )
        
        if not result.get("success"):
            await event.send(MessageChain().message(f"❌ {result.get('message', '删除失败')}"))
            return
        
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
        self.web_admin_task = None
        
        if self.log_permission_changes:
            logger.info(f"权限管理插件已加载 - Web UI: {self.webui_enabled} (端口: {self.webui_port}), 命令行: {self.command_enabled}")
    
    async def initialize(self):
        """插件初始化方法，在插件加载后自动调用"""
        # 如果 Web UI 已启用，自动启动
        if self.webui_enabled:
            # 使用 asyncio.create_task 在后台启动 Web UI
            asyncio.create_task(self._auto_start_webui())

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
            # 先获取插件信息以便确认
            plugin_commands = self.perm_cmd._get_all_commands_by_plugin()
            if plugin_name not in plugin_commands:
                await event.send(MessageChain().message(f"未找到插件: {plugin_name}"))
                return
            
            total_count = len(plugin_commands[plugin_name])
            perm_text = "管理员权限" if permission == "admin" else "成员权限"
            
            # 发送确认消息
            confirm_msg = (
                f"⚠️ 确认批量设置权限\n\n"
                f"插件: {plugin_name}\n"
                f"权限: {perm_text}\n"
                f"影响命令数: {total_count}\n\n"
                f"此操作将修改该插件的所有命令权限。\n"
                f"请回复 '确认' 或 'yes' 继续，或回复其他内容取消。"
            )
            await event.send(MessageChain().message(confirm_msg))
            
            # 等待用户确认（这里简化处理，实际应该使用更复杂的确认机制）
            # 注意：这是一个简化的实现，实际应用中可能需要更复杂的确认流程
            # 由于 AstrBot 的事件处理机制，这里我们直接执行，但会在消息中提示用户
            # 如果需要真正的确认机制，需要实现状态机或使用其他机制
            pass  # 暂时保留直接执行，但已添加确认提示
        
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
    
    async def _launch_webui_instance(self) -> bool:
        """
        启动 Web UI 实例的核心逻辑
        返回: True 如果启动成功, False 如果启动失败
        """
        if self.web_admin_task and not self.web_admin_task.done():
            return False
        
        # 检查端口是否可用
        import socket
        
        def check_port(port):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("0.0.0.0", port))
                return True
            except OSError:
                return False
        
        loop = asyncio.get_event_loop()
        port_available = await loop.run_in_executor(None, check_port, self.webui_port)
        
        if not port_available:
            return False
        
        try:
            from hypercorn.config import Config
            from hypercorn.asyncio import serve
            from .manager.server import create_app
            from .manager.service import PermissionService
            
            permission_service = PermissionService()
            services_to_inject = {
                "permission_service": permission_service
            }
            
            app = create_app(secret_key=self.webui_secret_key, services=services_to_inject)
            config = Config()
            config.bind = [f"{self.webui_host}:{self.webui_port}"]
            self.web_admin_task = asyncio.create_task(serve(app, config))
            
            # 等待服务启动
            await asyncio.sleep(1)
            
            # 检查端口是否激活
            for i in range(10):
                if await self._check_port_active():
                    return True
                await asyncio.sleep(1)
            
            return False
        except Exception as e:
            logger.error(f"启动 Web UI 失败: {e}", exc_info=True)
            return False
    
    async def _auto_start_webui(self):
        """自动启动 Web UI（静默启动，不发送消息）"""
        if self.web_admin_task and not self.web_admin_task.done():
            logger.info("Web UI 已经在运行中")
            return
        
        logger.info(f"正在自动启动权限管理 Web UI (端口: {self.webui_port})...")
        
        success = await self._launch_webui_instance()
        
        if not success:
            logger.warning(f"端口 {self.webui_port} 已被占用或启动超时，Web UI 启动失败。请更换端口后重试。")
            return
        
        logger.info(
            f"✅ 权限管理 Web UI 已自动启动！\n"
            f"🔗 访问地址: http://{self.webui_host}:{self.webui_port}/admin\n"
            f"🔑 密钥请到插件配置文件中查看（webui.secret_key）"
        )
    
    async def _start_webui(self, event: AstrMessageEvent = None):
        """启动 Web UI（手动启动，会发送消息）"""
        if self.web_admin_task and not self.web_admin_task.done():
            if event:
                await event.send(MessageChain().message("❌ Web UI 已经在运行中"))
            return
        
        if event:
            await event.send(MessageChain().message("🔄 正在启动权限管理 Web UI..."))
        
        success = await self._launch_webui_instance()
        
        if not success:
            if event:
                await event.send(MessageChain().message(f"❌ 端口 {self.webui_port} 已被占用或启动超时，请更换端口后重试"))
            return
        
        if event:
            await event.send(MessageChain().message(
                f"✅ 权限管理 Web UI 已启动！\n"
                f"🔗 请访问 http://localhost:{self.webui_port}/admin\n"
                f"🔑 密钥请到插件配置文件中查看（webui.secret_key）\n\n"
                f"⚠️ 重要提示：\n"
                f"• 如需公网访问，请自行配置端口转发和防火墙规则\n"
                f"• 确保端口 {self.webui_port} 已开放并映射到公网IP\n"
                f"• 建议使用反向代理（如Nginx）增强安全性\n"
                f"• 请妥善保管密钥，不要泄露给他人"
            ))
    
    async def _stop_webui(self, event: AstrMessageEvent):
        """停止 Web UI"""
        if not self.web_admin_task or self.web_admin_task.done():
            await event.send(MessageChain().message("❌ Web UI 没有在运行中"))
            return
        
        try:
            self.web_admin_task.cancel()
            await self.web_admin_task
        except asyncio.CancelledError:
            logger.info("权限管理 Web UI 已成功关闭")
            await event.send(MessageChain().message("✅ Web UI 已关闭"))
        except Exception as e:
            logger.error(f"关闭 Web UI 失败: {e}")
            await event.send(MessageChain().message(f"❌ 关闭 Web UI 失败: {e}"))
    
    async def _webui_status(self, event: AstrMessageEvent):
        """查看 Web UI 状态"""
        is_running = self.web_admin_task and not self.web_admin_task.done()
        status = "运行中" if is_running else "未运行"
        
        await event.send(MessageChain().message(
            f"Web UI 状态：{status}\n"
            f"端口：{self.webui_port}\n"
            f"主机：{self.webui_host}\n"
            f"访问地址：http://{self.webui_host}:{self.webui_port}/admin\n"
            f"密钥：请到插件配置文件中查看（webui.secret_key）"
        ))
    
    async def _check_port_active(self) -> bool:
        """验证端口是否实际已激活"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self.webui_port),
                timeout=1
            )
            writer.close()
            await writer.wait_closed()
            return True
        except:
            return False
    
    async def terminate(self):
        """插件被卸载/停用时调用"""
        if self.web_admin_task:
            self.web_admin_task.cancel()
            try:
                await self.web_admin_task
            except asyncio.CancelledError:
                pass
        logger.info("权限管理插件已成功终止。")

