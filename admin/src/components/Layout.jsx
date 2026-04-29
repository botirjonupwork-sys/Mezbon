import { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, Avatar, Typography, Space, Drawer, Select, Badge, Tag, Tooltip } from 'antd'
import {
  DashboardOutlined, ShoppingCartOutlined, AppstoreOutlined,
  UserOutlined, StarOutlined, LogoutOutlined, SettingOutlined, TeamOutlined,
  CarOutlined, MenuOutlined, BranchesOutlined, LockOutlined,
  GiftOutlined, RobotOutlined, RocketOutlined, CreditCardOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '../store/auth'
import { useBranchStore } from '../store/branch'
import { getAdminBranches, getMyPlan } from '../api'

const { Header, Sider, Content } = Layout
const { Text } = Typography

// Tarif darajasiga rang
const PLAN_COLORS = {
  free:  'default',
  basic: 'blue',
  pro:   'gold',
}

// Asosiy menyu — ba'zi item'larga "feature" flag biriktirilgan
// Agar restoran tarifi shu featureni qo'llab-quvvatlamasa, item "Locked" ko'rinadi
const topMenuConfig = [
  { key: '/',         icon: <DashboardOutlined />,    label: 'Dashboard' },
  { key: '/orders',   icon: <ShoppingCartOutlined />, label: 'Zakazlar'  },
  { key: '/menu',     icon: <AppstoreOutlined />,     label: 'Menyu'     },
  { key: '/users',    icon: <UserOutlined />,         label: 'Mijozlar'  },
  { key: '/reviews',  icon: <StarOutlined />,         label: 'Baholar'   },
  { key: '/couriers', icon: <CarOutlined />,          label: 'Kuryerlar' },
]

const allBottomMenuItems = [
  { key: '/billing',  icon: <CreditCardOutlined />, label: 'Tariflar' },
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
  const [plan, setPlan] = useState(null)         // { id, name, slug, ... }
  const [features, setFeatures] = useState({})   // { catering: bool, ai_agent: bool, yandex: bool }

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

  // Load current plan + features
  useEffect(() => {
    if (!restaurantId) {
      setPlan(null)
      setFeatures({})
      return
    }
    getMyPlan({ restaurant_id: restaurantId })
      .then((r) => {
        setPlan(r.data?.plan || null)
        setFeatures(r.data?.features || {})
      })
      .catch(() => {
        setPlan(null)
        setFeatures({})
      })
  }, [restaurantId])

  // Tariff darajasiga qarab "Locked" funksiyalarni belgilash. Hozircha asosiy
  // navigatsiya pages'i tarifga bog'lanmagan (Catering Menyu ichida sub-tab,
  // AI agent va Yandex Settings ichida sub-bo'limlar). Lekin quyida
  // virtual "Locked" ma'lumotchi qatorlar qo'shamiz — foydalanuvchi tarifda
  // nima bor/yo'qligini darhol ko'rishi uchun.
  const lockedFeatureItems = []
  if (restaurantId && !features.catering) {
    lockedFeatureItems.push({
      key: 'locked-catering', icon: <GiftOutlined />, disabled: true,
      label: <Tooltip title="Catering joriy tarifda mavjud emas — tarifni yangilang">
        <span style={{ opacity: 0.55 }}>Catering <LockOutlined style={{ marginLeft: 6 }} /></span>
      </Tooltip>,
    })
  }
  if (restaurantId && !features.yandex) {
    lockedFeatureItems.push({
      key: 'locked-yandex', icon: <RocketOutlined />, disabled: true,
      label: <Tooltip title="Yandex Delivery joriy tarifda mavjud emas">
        <span style={{ opacity: 0.55 }}>Yandex Delivery <LockOutlined style={{ marginLeft: 6 }} /></span>
      </Tooltip>,
    })
  }
  if (restaurantId && !features.ai_agent) {
    lockedFeatureItems.push({
      key: 'locked-ai', icon: <RobotOutlined />, disabled: true,
      label: <Tooltip title="AI Call Operator faqat Pro tarifida">
        <span style={{ opacity: 0.55 }}>AI Operator <LockOutlined style={{ marginLeft: 6 }} /></span>
      </Tooltip>,
    })
  }

  const topMenuItems = [...topMenuConfig, ...lockedFeatureItems]

  const handleMenuClick = ({ key }) => {
    navigate(key)
    if (isMobile) setDrawerOpen(false)
  }

  const siderContent = (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '20px 16px', borderBottom: '1px solid #303030', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <Text strong style={{ color: '#fa8c16', fontSize: 16 }}>
            {admin?.name || 'Admin'}
          </Text>
          {plan && (
            <Tooltip title={`Joriy tarif: ${plan.name}`}>
              <Tag color={PLAN_COLORS[plan.slug] || 'default'} style={{ margin: 0, textTransform: 'uppercase', fontWeight: 600 }}>
                {plan.slug || plan.name}
              </Tag>
            </Tooltip>
          )}
        </div>
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
