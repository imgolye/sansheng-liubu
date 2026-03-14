import { Button, Card, List, Space, Table } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { formatListText, safeArray, statusTag } from "../ui.jsx";

function TasksView({ permissions, tasks, dashboard, onOpenCreateTask, onSelectTask }) {
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card
        title="交付执行台"
        extra={
          permissions.taskWrite ? (
            <Button type="primary" icon={<PlusOutlined />} onClick={onOpenCreateTask}>
              创建任务
            </Button>
          ) : null
        }
      >
        <Table
          rowKey="id"
          dataSource={tasks}
          onRow={(record) => ({
            onClick: () => onSelectTask(record.id),
          })}
          columns={[
            { title: "任务号", dataIndex: "id", width: 180 },
            { title: "标题", dataIndex: "title", ellipsis: true },
            { title: "状态", dataIndex: "state", width: 120, render: (value) => statusTag(value) },
            { title: "负责人", dataIndex: "currentAgentLabel", width: 160, ellipsis: true },
            { title: "签收", dataIndex: "owner", width: 140, ellipsis: true },
            { title: "更新时间", dataIndex: "updatedAgo", width: 120 },
          ]}
        />
      </Card>

      <Card title="交付物">
        <List
          dataSource={safeArray(dashboard.deliverables)}
          locale={{ emptyText: "当前还没有已归档交付物。" }}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                title={`${item.id} · ${item.title}`}
                description={formatListText([item.summary, item.output, item.updatedAgo])}
              />
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}

export default TasksView;
