# permission-manager

<div align="center">

_✨ AstrBot 批量权限管理插件 ✨_

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)

</div>

## 🤝 介绍

批量权限管理插件，提供便捷的批量权限设置功能。对于有几十个命令的插件，不再需要一个个设置权限，一键批量设置整个插件的所有命令权限。

**主要特性：**
- ✅ **批量操作**：一键批量设置整个插件的所有命令权限
- ✅ **可视化界面**：提供 Web UI 界面，直观展示权限状态
- ✅ **命令行工具**：提供 `/perm` 系列命令，方便命令行操作
- ✅ **完全兼容**：与原有的 `/alter_cmd` 命令完全兼容，使用相同的配置存储
- ✅ **实时生效**：设置后立即生效，无需重启

## 📦 安装

### 方式一：从插件市场安装（推荐）

在 AstrBot 的插件市场中搜索 `permission-manager`，点击安装即可。

### 方式二：手动安装

```bash
# 克隆仓库到插件目录
cd /path/to/AstrBot/data/plugins
git clone https://github.com/your-repo/permission-manager.git

# 重启 AstrBot
```

## 🐔 使用说明

### 命令行使用

#### 1. 查看插件列表

```
/perm list
```

列出所有已启用的插件及其命令数量。

#### 2. 查看插件命令详情

```
/perm plugin <插件名>
```

列出指定插件的所有命令及其当前权限状态。

**示例：**
```
/perm plugin astrbot
```

#### 3. 批量设置插件权限

```
/perm set plugin <插件名> <admin/member>
```

批量设置指定插件的所有命令权限。

**示例：**
```
/perm set plugin astrbot admin    # 将所有命令设为管理员权限
/perm set plugin astrbot member   # 将所有命令设为成员权限
```

#### 4. 设置单个命令权限

```
/perm set command <插件名> <命令名> <admin/member>
```

设置指定插件的单个命令权限。

**示例：**
```
/perm set command astrbot help admin
```

#### 5. 查看帮助

```
/perm help
```

显示详细的使用帮助。

### Web UI 使用

#### 方式一：独立 Web UI（推荐）

插件提供独立的 Web UI 界面，可以单独访问：

1. **启动 Web UI**：
   ```
   /perm webui start
   ```

2. **访问 Web UI**：
   - 打开浏览器访问：`http://localhost:8888/admin`（默认端口 8888）
   - 使用配置的密钥登录

3. **管理权限**：
   - 在首页查看所有插件列表
   - 点击插件名称查看该插件的所有命令
   - 批量设置或单独设置命令权限

4. **停止 Web UI**：
   ```
   /perm webui stop
   ```

5. **查看状态**：
   ```
   /perm webui status
   ```

#### 方式二：AstrBot 主 Web UI

也可以使用 AstrBot 主 Web UI 中的权限管理功能：

1. 打开 AstrBot 的 Web 界面（默认端口 6185）
2. 在侧边栏导航中找到 **"权限管理"** 菜单
3. 从左侧列表中选择要管理的插件
4. 右侧显示该插件的所有命令和指令组
5. 点击 **"全部设为管理员"** 或 **"全部设为成员"** 按钮进行批量设置
6. 或为每个命令单独设置权限

### 权限说明

- **admin**：仅管理员可使用
- **member**：所有成员可使用（管理员也可用）

## 🔧 与原有功能的关系

本插件与 AstrBot 自带的 `/alter_cmd` 命令完全兼容：

| 功能 | `/alter_cmd` | `/perm` | Web UI |
|------|-------------|---------|--------|
| 单个命令设置 | ✅ | ✅ | ✅ |
| 批量设置 | ❌ | ✅ | ✅ |
| 查看命令列表 | ❌ | ✅ | ✅ |
| 图形化界面 | ❌ | ❌ | ✅ |

**配置存储：**
- 所有功能都使用相同的 `alter_cmd` 全局配置存储
- 配置格式：`{插件名: {命令名: {permission: "admin"|"member"}}}`
- 设置后立即生效，无需重启

## 💡 使用场景

### 场景一：批量设置插件权限

**之前（很麻烦）：**
```
/alter_cmd cmd1 admin
/alter_cmd cmd2 admin
/alter_cmd cmd3 admin
... (重复几十次)
```

**现在（一条命令）：**
```
/perm set plugin 插件名 admin
```

### 场景二：查看插件所有命令

**之前：**
- 需要手动查看插件代码或文档

**现在：**
```
/perm plugin 插件名
```

或在 Web UI 中直观查看。

### 场景三：图形化操作

**之前：**
- 只能使用命令行

**现在：**
- 在 Web UI 中点击按钮即可完成操作

## 📝 注意事项

1. 所有命令都需要管理员权限才能执行
2. 批量设置会覆盖所有命令的权限配置
3. 设置后立即生效，无需重启
4. 与原有的 `/alter_cmd` 命令完全兼容，可以混用

## ⚙️ Web UI 配置

### 独立 Web UI 配置

插件提供独立的 Web UI，可以在插件配置中设置：

1. **配置文件位置**：`data/config/plugins/permission-manager_config.json`
2. **配置项**：
   ```json
   {
     "webui": {
       "enabled": true,
       "secret_key": "PermissionManager",
       "port": 8888,
       "host": "0.0.0.0"
     }
   }
   ```
3. **配置说明**：
   - `enabled`: 是否启用 Web UI（默认：true）
   - `secret_key`: 登录密钥（默认：PermissionManager）
   - `port`: Web UI 端口（默认：8888）
   - `host`: 监听地址（默认：0.0.0.0，表示所有网络接口）


## 🔗 相关链接

- [AstrBot 官方文档](https://astrbot.app)
- [AstrBot GitHub](https://github.com/Soulter/AstrBot)

## 📄 许可证

MIT License

