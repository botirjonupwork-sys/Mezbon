import { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, Avatar, Typography, Space, Drawer } from 'antd'
import {
  DashboardOutlined, ShoppingCartOutlined, AppstoreOutlined,
  UserOutlined, StarOutlined, LogoutOutlined, SettingOutlined, TeamOutlined,
  CarOutlined, MenuOutlined
} from '@ant-design/icons'
import { useAuthStore } from '../store/auth'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const topMenuItems = [
  { key: '/',        icon: <DashboardOutlined />,    label: 'Dashboard' },
  { key: '/orders',  icon: <ShoppingCartOutlined />, label: 'Zakazlar'  },
  { key: '/menu',    icon: <AppstoreOutlined />,     label: 'Menyu'     },
  { key: '/users',   icon: <UserOutlined />,         label: 'Mijozlar'  },
  { key: '/reviews', icon: <StarOutlined />,         label: 'Baholar'   },
  { key: '/couriers', icon: <CarOutlined />,         label: 'Kuryerlar' },
]

const bottomMenuItems = [
  { key: '/admins',   icon: <TeamOutlined />,    label: 'Adminlar'   },
  { key: '/settings', icon: <SettingOutlined />, label: 'Sozlamalar' },
]

export default function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { admin, logout } = useAuthStore()
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const handleMenuClick = ({ key }) => {
    navigate(key)
    if (isMobile) setDrawerOpen(false)
  }

  const siderContent = (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '20px 16px', borderBottom: '1px solid #303030', flexShrink: 0 }}>
        <Text strong style={{ color: '#fa8c16', fontSize: 16 }}>
          Muhsina Admin
        </Text>
      </div>
      <div style={{ flex: 1 }}>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={topMenuItems}
          onClick={handleMenuClick}
          style={{ marginTop: 8, borderRight: 0 }}
        />
      </div>
      <div style={{ borderTop: '1px solid #303030', flexShrink: 0 }}>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={bottomMenuItems}
          onClick={handleMenuClick}
          style={{ borderRight: 0 }}
        />
      </div>
    </div>
  )

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {!isMobile && (
        <Sider
          theme="dark"
          width={220}
          style={{ overflow: 'hidden', height: '100vh', position: 'sticky', top: 0, left: 0 }}
        >
          {siderContent}
        </Sider>
      )}

      {isMobile && (
        <Drawer
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          width={240}
          styles={{ body: { padding: 0, background: '#001529' } }}
          closable={false}
        >
          {siderContent}
        </Drawer>
      )}

      <Layout>
        <Header style={{
          background: '#fff', padding: '0 16px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          boxShadow: '0 1px 4px rgba(0,0,0,0.1)',
        }}>
          <div>
            {isMobile && (
              <Button
                type="text"
                icon={<MenuOutlined />}
                onClick={() => setDrawerOpen(true)}
                style={{ fontSize: 18 }}
              />
            )}
          </div>
          <Space>
            <Avatar icon={<UserOutlined />} style={{ background: '#fa8c16' }} size={isMobile ? 'small' : 'default'} />
            {!isMobile && <Text strong>{admin?.name || 'Admin'}</Text>}
            <Button icon={<LogoutOutlined />} type="text" danger onClick={logout} size={isMobile ? 'small' : 'middle'}>
              {isMobile ? '' : 'Chiqish'}
            </Button>
          </Space>
        </Header>

        <Content style={{ margin: isMobile ? 8 : 24, minHeight: 280 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
