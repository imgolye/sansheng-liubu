import { lazy, startTransition, Suspense, useDeferredValue, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  App as AntdApp,
  Alert,
  Badge,
  Button,
  Card,
  ConfigProvider,
  Input,
  Layout,
  Menu,
  Segmented,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import enUS from "antd/locale/en_US";
import zhCN from "antd/locale/zh_CN";
import {
  ApiOutlined,
  ApartmentOutlined,
  BookOutlined,
  CommentOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  LogoutOutlined,
  ReloadOutlined,
  SettingOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { ApiError, getConversationTranscript, getDashboard, getSession, loginWithPassword, loginWithToken, logout, postAction } from "./api";
import { safeArray } from "./ui.jsx";
import { buildTranslator, normalizeLocale } from "./i18n.jsx";
import ViewErrorBoundary from "./components/ViewErrorBoundary.jsx";

const { Header, Sider, Content } = Layout;
const { Title, Paragraph, Text } = Typography;


const LoginPage = lazy(() => import("./LoginPage"));
const OverviewView = lazy(() => import("./views/OverviewView"));
const ManagementView = lazy(() => import("./views/ManagementView"));
const OrchestrationView = lazy(() => import("./views/OrchestrationView"));
const ContextHubView = lazy(() => import("./views/ContextHubView"));
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

const LOCALE_STORAGE_KEY = "mission-control.locale";
const POLL_INTERVAL_MS = 8000;

function ViewSkeleton({ compact = false }) {
  return (
    <Card className="workspace-card">
      <Space direction="vertical" size={18} style={{ width: "100%" }}>
        <Skeleton.Button active block style={{ width: compact ? "48%" : "28%", height: 18 }} />
        <Skeleton.Input active block style={{ height: compact ? 36 : 44 }} />
        <Skeleton active paragraph={{ rows: compact ? 3 : 6 }} title={false} />
      </Space>
    </Card>
  );
}

function normalizePath(pathname) {
  if (!pathname || pathname === "/") {
    return "/overview";
  }
  return pathname;
}

function menuItems(t) {
  return [
    { key: "/overview", icon: <DashboardOutlined />, label: t("menu.overview") },
    { key: "/management", icon: <DeploymentUnitOutlined />, label: t("menu.management") },
    { key: "/orchestration", icon: <ApartmentOutlined />, label: t("menu.orchestration") },
    { key: "/context", icon: <BookOutlined />, label: t("menu.context") },
    { key: "/agents", icon: <TeamOutlined />, label: t("menu.agents") },
    { key: "/tasks", icon: <UnorderedListOutlined />, label: t("menu.tasks") },
    { key: "/conversations", icon: <CommentOutlined />, label: t("menu.conversations") },
    { key: "/activity", icon: <ThunderboltOutlined />, label: t("menu.activity") },
    { key: "/themes", icon: <ApartmentOutlined />, label: t("menu.themes") },
    { key: "/skills", icon: <SettingOutlined />, label: t("menu.skills") },
    { key: "/openclaw", icon: <ApiOutlined />, label: t("menu.openclaw") },
    { key: "/admin", icon: <SettingOutlined />, label: t("menu.admin") },
  ];
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
  const [localePreference, setLocalePreference] = useState(() => {
    try {
      return localStorage.getItem(LOCALE_STORAGE_KEY) || "auto";
    } catch {
      return "auto";
    }
  });
  const [isOffline, setIsOffline] = useState(() => !navigator.onLine);
  const dashboardRefreshRef = useRef(() => Promise.resolve());
  const currentPath = normalizePath(location.pathname);
  const deferredSearch = useDeferredValue(search);
  const localeKey = localePreference === "auto" ? normalizeLocale(dashboard?.theme?.language) : normalizeLocale(localePreference);
  const t = buildTranslator(localeKey);
  const currentAntdLocale = localeKey === "en" ? enUS : zhCN;
  const currentMenuItems = menuItems(t);

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

  useEffect(() => {
    dashboardRefreshRef.current = refreshDashboard;
  });

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

    let pollTimer = 0;
    let reconnectTimer = 0;
    let eventSource = null;
    let disposed = false;

    const stopPolling = () => {
      if (pollTimer) {
        window.clearInterval(pollTimer);
        pollTimer = 0;
      }
    };

    const startPolling = () => {
      if (pollTimer) {
        return;
      }
      pollTimer = window.setInterval(() => {
        void dashboardRefreshRef.current({ silent: true });
      }, POLL_INTERVAL_MS);
    };

    const closeStream = () => {
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
    };

    const connectStream = () => {
      if (disposed || !window.EventSource) {
        startPolling();
        return;
      }

      closeStream();
      eventSource = new window.EventSource("/events", { withCredentials: true });
      eventSource.addEventListener("dashboard", () => {
        void dashboardRefreshRef.current({ silent: true });
      });
      eventSource.onopen = () => {
        if (reconnectTimer) {
          window.clearTimeout(reconnectTimer);
          reconnectTimer = 0;
        }
        stopPolling();
      };
      eventSource.onerror = () => {
        closeStream();
        startPolling();
        if (!disposed && navigator.onLine) {
          if (reconnectTimer) {
            window.clearTimeout(reconnectTimer);
          }
          reconnectTimer = window.setTimeout(connectStream, 4000);
        }
      };
    };

    connectStream();
    startPolling();

    return () => {
      disposed = true;
      stopPolling();
      closeStream();
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
    };
  }, [session]);

  useEffect(() => {
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, localePreference);
    } catch {
      // Ignore storage failures.
    }
  }, [localePreference]);

  useEffect(() => {
    document.documentElement.lang = localeKey === "en" ? "en" : "zh-CN";
  }, [localeKey]);

  useEffect(() => {
    function handleOnline() {
      setIsOffline(false);
      void dashboardRefreshRef.current({ silent: true });
    }
    function handleOffline() {
      setIsOffline(true);
    }
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

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
  const isSnapshot = Boolean(dashboard?.runtime?.offlineSnapshot);

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
      message.success(localeKey === "en" ? "Signed in" : "登录成功");
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
      message.success(localeKey === "en" ? "Signed in" : "登录成功");
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
    const viewProps = { dashboard, agents, tasks, permissions, sessions, t, localeKey };
    switch (currentPath) {
      case "/agents":
        return <AgentsView {...viewProps} onSelectAgent={setSelectedAgentId} onNavigate={(path) => navigate(path)} />;
      case "/management":
        return (
          <ManagementView
            {...viewProps}
            onCreateRun={(values) => runAction("/api/actions/management/run/create", values)}
            onUpdateRun={(values) => runAction("/api/actions/management/run/update", values)}
            onSaveRule={(values) => runAction("/api/actions/management/rule/save", values)}
            onSaveChannel={(values) => runAction("/api/actions/management/channel/save", values)}
            onTestChannel={(values) => runAction("/api/actions/management/channel/test", values)}
            onBootstrapRules={() => runAction("/api/actions/management/bootstrap", {})}
            onExportReport={() => runAction("/api/actions/management/report/export", {})}
            onSelectTask={setSelectedTaskId}
            onOpenConversation={openConversation}
          />
        );
      case "/orchestration":
        return (
          <OrchestrationView
            {...viewProps}
            onSaveWorkflow={(values) => runAction("/api/actions/orchestration/workflow/save", values)}
            onSavePolicy={(values) => runAction("/api/actions/orchestration/policy/save", values)}
          />
        );
      case "/context":
        return <ContextHubView {...viewProps} onAction={runAction} />;
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
        return <OpenClawView {...viewProps} onAction={runAction} />;
      case "/admin":
        return (
          <AdminView
            {...viewProps}
            onRegisterInstance={(values) => runAction("/api/actions/admin/instance/register", values)}
            onCreateUser={(values) => runAction("/api/actions/admin/user/create", values)}
            onCreateTenant={(values) => runAction("/api/actions/admin/tenant/save", values)}
            onBindTenantInstallation={(values) => runAction("/api/actions/admin/tenant/installation/save", values)}
            onCreateTenantApiKey={(values) => runAction("/api/actions/admin/tenant/api-key/create", values)}
          />
        );
      case "/overview":
      default:
        return <OverviewView {...viewProps} onNavigate={(path) => navigate(path)} onOpenCreateTask={() => setCreateTaskOpen(true)} />;
    }
  }

  if (booting) {
    return (
      <div className="center-screen">
        <div className="shell-boot-card">
          <ViewSkeleton />
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <Suspense fallback={<div className="center-screen"><div className="shell-boot-card"><ViewSkeleton compact /></div></div>}>
        <LoginPage
          t={t}
          authMode={authMode}
          loading={loading}
          onPasswordLogin={handlePasswordLogin}
          onTokenLogin={handleTokenLogin}
        />
      </Suspense>
    );
  }

  const visibleMenuItems = currentMenuItems.filter((item) => item.key !== "/admin" || permissions.auditView || permissions.adminWrite);

  return (
    <ConfigProvider
      locale={currentAntdLocale}
      theme={{
        token: {
          colorPrimary: "#b34722",
          borderRadius: 10,
          fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
          colorBgLayout: "#f5f7fa",
        },
      }}
    >
      <Layout className="mission-layout">
        <Sider theme="light" width={236} breakpoint="lg" collapsedWidth={88} className="mission-sider">
          <div className="brand-panel">
            <div className="brand-mark">三</div>
            <Text className="section-kicker">Sansheng Liubu</Text>
            <Title level={3}>Mission Control</Title>
            <Paragraph type="secondary">
              {t("app.shellSummary")}
            </Paragraph>
            <div className="brand-chip-row">
              <Tag color="processing">{dashboard?.theme?.displayName || t("common.unknown")}</Tag>
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
              <Text className="section-kicker">{t("app.operationsLayer")}</Text>
              <Title level={2}>{visibleMenuItems.find((item) => item.key === currentPath)?.label || t("menu.overview")}</Title>
              <div className="header-meta">
                <Text type="secondary">{dashboard?.ownerTitle || t("app.missionControl")}</Text>
                <span className="header-dot" />
                <Text type="secondary">{dashboard?.openclawDir || ""}</Text>
              </div>
            </div>

            <Space wrap size={12} className="header-tools">
              <Segmented
                size="small"
                value={localePreference}
                options={[
                  { value: "auto", label: t("common.auto") },
                  { value: "zh", label: t("common.chinese") },
                  { value: "en", label: t("common.english") },
                ]}
                onChange={(value) => setLocalePreference(String(value))}
              />
              <Input.Search
                allowClear
                placeholder={t("common.searchPlaceholder")}
                value={search}
                onChange={(event) => {
                  const nextValue = event.target.value;
                  startTransition(() => {
                    setSearch(nextValue);
                  });
                }}
                style={{ width: 320 }}
              />
              <Badge status="processing" text={`${t("app.headerSubtitle")} ${dashboard?.generatedAgo || t("common.justNow")}`} />
              <Tag color="gold">{session?.session?.displayName || "Local Access"}</Tag>
              <Button icon={<ReloadOutlined />} loading={loading} onClick={() => refreshDashboard()}>
                {t("common.refresh")}
              </Button>
              <Button icon={<LogoutOutlined />} onClick={handleLogout}>
                {t("common.logout")}
              </Button>
            </Space>
          </Header>

          <Content className="mission-content">
            {isOffline ? (
              <Alert type="warning" banner showIcon={false} message={t("app.offlineBanner")} style={{ marginBottom: 16 }} />
            ) : null}
            {isSnapshot ? (
              <Alert type="info" banner showIcon={false} message={t("app.staleBanner")} style={{ marginBottom: 16 }} />
            ) : null}
            {!dashboard ? (
              <ViewSkeleton />
            ) : (
              <ViewErrorBoundary
                resetKey={`${currentPath}:${dashboard?.signature || ""}`}
                title={t("app.moduleErrorTitle")}
                description={t("app.moduleErrorDescription")}
                retryLabel={t("app.moduleErrorRetry")}
                onError={() => message.error(t("app.moduleErrorToast"))}
              >
                <Suspense fallback={<ViewSkeleton />}>
                  {renderCurrentView()}
                </Suspense>
              </ViewErrorBoundary>
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
    </ConfigProvider>
  );
}

export default App;
