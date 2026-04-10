import { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, Avatar, Typography, Space, Drawer, Select } from 'antd'
import {
  DashboardOutlined, ShoppingCartOutlined, AppstoreOutlined,
  UserOutlined, StarOutlined, LogoutOutlined, SettingOutlined, TeamOutlined,
  CarOutlined, MenuOutlined, BranchesOutlined
} from '@ant-design/icons'
import { useAuthStore } from '../store/auth'
import { useBranchStore } from '../store/branch'
import { getAdminBranches } from '../api'

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

const allBottomMenuItems = [
  { key: '/admins',   icon: <TeamOutlined />,    label: 'Adminlar', superOnly: true },
  { key: '/settings', icon: <SettingOutlined />, label: 'Sozlamalar' },
]

export default function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { admin, logout, restaurantId } = useAuthStore()
  const { branches, selectedBranchId, setBranches, selectBranch } = useBranchStore()
  const bottomMenuItems = allBottomMenuItems.filter((i) => !i.superOnly || !restaurantId)
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Load branches
  useEffect(() => {
    if (!restaurantId) {
      setBranches([])
      return
    }
    getAdminBranches({ restaurant_id: restaurantId })
      .then((r) => {
        const list = r.data || []
        setBranches(list)
        if (!selectedBranchId && list.length === 1) selectBranch(list[0].id)
      })
      .catch(() => setBranches([]))
  }, [restaurantId])

  const handleMenuClick = ({ key }) => {
    navigate(key)
    if (isMobile) setDrawerOpen(false)
  }

  const siderContent = (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '20px 16px', borderBottom: '1px solid #303030', flexShrink: 0 }}>
        <Text strong style={{ color: '#fa8c16', fontSize: 16 }}>
          {admin?.name || 'Admin'}
        </Text>
        {branches.length > 0 && (
          <Select
            value={selectedBranchId}
            onChange={selectBranch}
            style={{ width: '100%', marginTop: 10 }}
            size="small"
            suffixIcon={<BranchesOutlined style={{ color: '#fa8c16' }} />}
            options={[
              { value: null, label: 'Barcha filiallar' },
              ...branches.map((b) => ({ value: b.id, label: b.name })),
            ]}
          />
        )}
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
