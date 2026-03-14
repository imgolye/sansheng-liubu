import { lazy, startTransition, Suspense, useDeferredValue, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  App as AntdApp,
  Badge,
  Button,
  Card,
  Input,
  Layout,
  Menu,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import {
  ApiOutlined,
  ApartmentOutlined,
  CommentOutlined,
  DashboardOutlined,
  LogoutOutlined,
  ReloadOutlined,
  SettingOutlined,
  TeamOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { ApiError, getConversationTranscript, getDashboard, getSession, loginWithPassword, loginWithToken, logout, postAction } from "./api";
import { safeArray } from "./ui.jsx";

const { Header, Sider, Content } = Layout;
const { Title, Paragraph, Text } = Typography;


const LoginPage = lazy(() => import("./LoginPage"));
const OverviewView = lazy(() => import("./views/OverviewView"));
const AgentsView = lazy(() => import("./views/AgentsView"));
const TasksView = lazy(() => import("./views/TasksView"));
const ConversationsView = lazy(() => import("./views/ConversationsView"));
const ActivityView = lazy(() => import("./views/ActivityView"));
const ThemesView = lazy(() => import("./views/ThemesView"));
const SkillsView = lazy(() => import("./views/SkillsView"));
const OpenClawView = lazy(() => import("./views/OpenClawView"));
const AdminView = lazy(() => import("./views/AdminView"));
const AgentDrawer = lazy(() => import("./components/AgentDrawer"));
const TaskDrawer = lazy(() => import("./components/TaskDrawer"));
const CreateTaskModal = lazy(() => import("./components/CreateTaskModal"));

const MENU_ITEMS = [
  { key: "/overview", icon: <DashboardOutlined />, label: "总览" },
  { key: "/agents", icon: <TeamOutlined />, label: "Agent 运营" },
  { key: "/tasks", icon: <UnorderedListOutlined />, label: "交付执行" },
  { key: "/conversations", icon: <CommentOutlined />, label: "会话中心" },
  { key: "/activity", icon: <ThunderboltOutlined />, label: "活动时间线" },
  { key: "/themes", icon: <ApartmentOutlined />, label: "主题中心" },
  { key: "/skills", icon: <SettingOutlined />, label: "Skills Center" },
  { key: "/openclaw", icon: <ApiOutlined />, label: "OpenClaw" },
  { key: "/admin", icon: <SettingOutlined />, label: "商业后台" },
];

function normalizePath(pathname) {
  if (!pathname || pathname === "/") {
    return "/overview";
  }
  return pathname;
}

function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const { message } = AntdApp.useApp();
  const [booting, setBooting] = useState(true);
  const [session, setSession] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [authMode, setAuthMode] = useState("token");
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [selectedConversationKey, setSelectedConversationKey] = useState("");
  const [transcript, setTranscript] = useState(null);
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const [createTaskOpen, setCreateTaskOpen] = useState(false);
  const currentPath = normalizePath(location.pathname);
  const deferredSearch = useDeferredValue(search);

  async function refreshDashboard({ silent = false } = {}) {
    if (!session) {
      return;
    }
    if (!silent) {
      setLoading(true);
    }
    try {
      const payload = await getDashboard();
      setDashboard(payload);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setSession(null);
        navigate("/login", { replace: true });
      } else if (!silent) {
        message.error(error.message);
      }
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }

  async function bootstrap() {
    setBooting(true);
    try {
      const auth = await getSession();
      setAuthMode(auth.authMode || "token");
      if (!auth.ok) {
        setSession(null);
        setDashboard(null);
        return;
      }
      setSession(auth);
      const payload = await getDashboard();
      setDashboard(payload);
    } catch (error) {
      message.error(error.message);
    } finally {
      setBooting(false);
    }
  }

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (booting) {
      return;
    }
    if (!session && currentPath !== "/login") {
      navigate("/login", { replace: true });
      return;
    }
    if (session && currentPath === "/login") {
      navigate("/overview", { replace: true });
    }
  }, [booting, session, currentPath, navigate]);

  useEffect(() => {
    if (!session) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      void refreshDashboard({ silent: true });
    }, 8000);
    return () => window.clearInterval(timer);
  }, [session]);

  const permissions = dashboard?.runtime?.permissions || session?.permissions || {};
  const actionToken = dashboard?.runtime?.actionToken || session?.actionToken || "";
  const normalizedSearch = deferredSearch.trim().toLowerCase();
  const agents = safeArray(dashboard?.agents).filter((agent) =>
    !normalizedSearch || JSON.stringify(agent).toLowerCase().includes(normalizedSearch),
  );
  const tasks = safeArray(dashboard?.taskIndex || dashboard?.tasks).filter((task) =>
    !normalizedSearch || JSON.stringify(task).toLowerCase().includes(normalizedSearch),
  );
  const sessions = safeArray(dashboard?.conversations?.sessions).filter((item) =>
    !normalizedSearch || JSON.stringify(item).toLowerCase().includes(normalizedSearch),
  );
  const selectedAgent = agents.find((agent) => agent.id === selectedAgentId) || null;
  const selectedTask = tasks.find((task) => task.id === selectedTaskId) || null;
  const selectedConversation = sessions.find((item) => item.key === selectedConversationKey) || null;

  async function runAction(path, payload, successMessage) {
    try {
      const response = await postAction(path, { ...payload, actionToken });
      if (response.dashboard) {
        setDashboard(response.dashboard);
      } else {
        await refreshDashboard({ silent: true });
      }
      if (successMessage || response.message) {
        message.success(successMessage || response.message);
      }
      return response;
    } catch (error) {
      message.error(error.message);
      throw error;
    }
  }

  async function handlePasswordLogin(username, password) {
    setLoading(true);
    try {
      const auth = await loginWithPassword(username, password);
      setSession(auth);
      setAuthMode(auth.authMode || "accounts");
      const payload = await getDashboard();
      setDashboard(payload);
      navigate("/overview", { replace: true });
      message.success("登录成功");
    } catch (error) {
      message.error(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleTokenLogin(token) {
    setLoading(true);
    try {
      const auth = await loginWithToken(token);
      setSession(auth);
      setAuthMode(auth.authMode || "token");
      const payload = await getDashboard();
      setDashboard(payload);
      navigate("/overview", { replace: true });
      message.success("登录成功");
    } catch (error) {
      message.error(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleLogout() {
    setLoading(true);
    try {
      await logout();
      setSession(null);
      setDashboard(null);
      setTranscript(null);
      navigate("/login", { replace: true });
    } catch (error) {
      message.error(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function openConversation(sessionRecord) {
    setSelectedConversationKey(sessionRecord.key);
    setTranscriptLoading(true);
    try {
      const payload = await getConversationTranscript(sessionRecord.agentId, sessionRecord.sessionId);
      setTranscript(payload.conversation || null);
    } catch (error) {
      message.error(error.message);
      setTranscript(null);
    } finally {
      setTranscriptLoading(false);
    }
  }

  function renderCurrentView() {
    const viewProps = { dashboard, agents, tasks, permissions, sessions };
    switch (currentPath) {
      case "/agents":
        return <AgentsView {...viewProps} onSelectAgent={setSelectedAgentId} />;
      case "/tasks":
        return <TasksView {...viewProps} onOpenCreateTask={() => setCreateTaskOpen(true)} onSelectTask={setSelectedTaskId} />;
      case "/conversations":
        return (
          <ConversationsView
            {...viewProps}
            selectedConversation={selectedConversation}
            selectedConversationKey={selectedConversationKey}
            transcript={transcript}
            transcriptLoading={transcriptLoading}
            onOpenConversation={openConversation}
            onSendConversation={async (values) => {
              const response = await runAction("/api/actions/conversations/send", {
                agentId: values.agentId,
                sessionId: values.continueSession ? selectedConversation?.sessionId || "" : "",
                message: values.message,
                thinking: values.thinking,
              });
              if (response.conversation) {
                setTranscript(response.conversation);
              }
            }}
          />
        );
      case "/activity":
        return <ActivityView {...viewProps} />;
      case "/themes":
        return <ThemesView {...viewProps} onSwitchTheme={(theme) => runAction("/api/actions/theme/switch", { theme })} />;
      case "/skills":
        return (
          <SkillsView
            {...viewProps}
            onPackageSkill={(slug) => runAction("/api/actions/skills/package", { slug })}
            onPublishSkill={(slug) => runAction("/api/actions/skills/publish", { slug })}
          />
        );
      case "/openclaw":
        return <OpenClawView {...viewProps} />;
      case "/admin":
        return (
          <AdminView
            {...viewProps}
            onRegisterInstance={(values) => runAction("/api/actions/admin/instance/register", values)}
            onCreateUser={(values) => runAction("/api/actions/admin/user/create", values)}
          />
        );
      case "/overview":
      default:
        return <OverviewView {...viewProps} />;
    }
  }

  if (booting) {
    return (
      <div className="center-screen">
        <Spin size="large" />
      </div>
    );
  }

  if (!session) {
    return (
      <Suspense fallback={<div className="center-screen"><Spin size="large" /></div>}>
        <LoginPage
          authMode={authMode}
          loading={loading}
          onPasswordLogin={handlePasswordLogin}
          onTokenLogin={handleTokenLogin}
        />
      </Suspense>
    );
  }

  const visibleMenuItems = MENU_ITEMS.filter((item) => item.key !== "/admin" || permissions.auditView || permissions.adminWrite);

  return (
    <>
      <Layout className="mission-layout">
        <Sider theme="light" width={236} breakpoint="lg" collapsedWidth={88} className="mission-sider">
          <div className="brand-panel">
            <div className="brand-mark">三</div>
            <Text className="section-kicker">Sansheng Liubu</Text>
            <Title level={3}>Mission Control</Title>
            <Paragraph type="secondary">
              商业化多 Agent 控制平面。统一查看协同、交付、对话和治理动作。
            </Paragraph>
            <div className="brand-chip-row">
              <Tag color="processing">{dashboard?.theme?.displayName || "未知主题"}</Tag>
              <Tag>{dashboard?.routerAgentId || "router"}</Tag>
            </div>
          </div>

          <Menu
            mode="inline"
            selectedKeys={[currentPath]}
            items={visibleMenuItems}
            onClick={({ key }) => navigate(key)}
            className="mission-menu"
          />
        </Sider>

        <Layout>
          <Header className="mission-header">
            <div className="header-intro">
              <Text className="section-kicker">Operations Layer</Text>
              <Title level={2}>{visibleMenuItems.find((item) => item.key === currentPath)?.label || "总览"}</Title>
              <div className="header-meta">
                <Text type="secondary">{dashboard?.ownerTitle || "Mission Control"}</Text>
                <span className="header-dot" />
                <Text type="secondary">{dashboard?.openclawDir || ""}</Text>
              </div>
            </div>

            <Space wrap size={12} className="header-tools">
              <Input.Search
                allowClear
                placeholder="搜索 Agent、任务、会话、主题"
                value={search}
                onChange={(event) => {
                  const nextValue = event.target.value;
                  startTransition(() => {
                    setSearch(nextValue);
                  });
                }}
                style={{ width: 320 }}
              />
              <Badge status="processing" text={`最近同步 ${dashboard?.generatedAgo || "刚刚"}`} />
              <Tag color="gold">{session?.session?.displayName || "Local Access"}</Tag>
              <Button icon={<ReloadOutlined />} loading={loading} onClick={() => refreshDashboard()}>
                立即刷新
              </Button>
              <Button icon={<LogoutOutlined />} onClick={handleLogout}>
                退出
              </Button>
            </Space>
          </Header>

          <Content className="mission-content">
            {!dashboard ? (
              <Card>
                <Spin />
              </Card>
            ) : (
              <Suspense fallback={<Card><Spin /></Card>}>
                {renderCurrentView()}
              </Suspense>
            )}
          </Content>
        </Layout>
      </Layout>

      <Suspense fallback={null}>
        <AgentDrawer agent={selectedAgent} open={Boolean(selectedAgent)} onClose={() => setSelectedAgentId("")} />
      </Suspense>

      <Suspense fallback={null}>
        <TaskDrawer task={selectedTask} open={Boolean(selectedTask)} onClose={() => setSelectedTaskId("")} permissions={permissions} onAction={runAction} />
      </Suspense>

      <Suspense fallback={null}>
        <CreateTaskModal
          open={createTaskOpen}
          onCancel={() => setCreateTaskOpen(false)}
          onAction={async (path, values) => {
            await runAction(path, values);
            setCreateTaskOpen(false);
          }}
        />
      </Suspense>
    </>
  );
}

export default App;
