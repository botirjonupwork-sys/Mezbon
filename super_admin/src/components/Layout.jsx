import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, Typography } from 'antd'
import { DashboardOutlined, ShopOutlined, LogoutOutlined, SettingOutlined, RobotOutlined, CrownOutlined, ControlOutlined, BankOutlined, LineChartOutlined } from '@ant-design/icons'
import { useAuthStore } from '../store/auth'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const menuItems = [
  { key: '/',            icon: <DashboardOutlined />, label: 'Dashboard' },
  { key: '/restaurants', icon: <ShopOutlined />,      label: 'Restoranlar' },
  { key: '/bots',        icon: <RobotOutlined />,     label: 'Botlar' },
  { key: '/tariffs',     icon: <CrownOutlined />,      label: 'Tariflar' },
  { key: '/finance',     icon: <BankOutlined />,       label: 'Moliya' },
  { key: '/analytics',   icon: <LineChartOutlined />,  label: 'Analytics' },
  { key: '/global',      icon: <ControlOutlined />,   label: 'Global sozlamalar' },
  { key: '/settings',    icon: <SettingOutlined />,   label: 'Sozlamalar' },
]

export default function SuperLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const logout = useAuthStore((s) => s.logout)

  const selectedKey = location.pathname === '/'
    ? '/'
    : '/' + location.pathname.split('/')[1]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={220} style={{ overflow: 'hidden', height: '100vh', position: 'sticky', top: 0 }}>
        <div style={{ padding: '20px 16px', borderBottom: '1px solid #303030' }}>
          <Text strong style={{ color: '#722ed1', fontSize: 15 }}>Mezbon · Super Admin</Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ marginTop: 8, borderRight: 0 }}
        />
      </Sider>

      <Layout>
        <Header style={{
          background: '#fff', padding: '0 24px',
          display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
          boxShadow: '0 1px 4px rgba(0,0,0,0.1)',
        }}>
          <Button icon={<LogoutOutlined />} type="text" danger onClick={logout}>
            Chiqish
          </Button>
        </Header>

        <Content style={{ margin: 24, minHeight: 280 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
