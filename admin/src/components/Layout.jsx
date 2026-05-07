import { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, Avatar, Typography, Space, Drawer, Select, Tag, Tooltip } from 'antd'
import {
  DashboardOutlined, ShoppingCartOutlined, AppstoreOutlined,
  UserOutlined, StarOutlined, LogoutOutlined, SettingOutlined, TeamOutlined,
  CarOutlined, MenuOutlined, BranchesOutlined, ShopOutlined,
  GiftOutlined, CreditCardOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '../store/auth'
import { useBranchStore } from '../store/branch'
import { getAdminBranches, getMyPlan, getSuperRestaurants } from '../api'

const { Header, Sider, Content } = Layout
const { Text } = Typography

// Tarif darajasiga rang
const PLAN_COLORS = {
  free:  'default',
  basic: 'blue',
  pro:   'gold',
}

// Asosiy menyu — `feature` flag biriktirilgan item'lar tarif featurelariga
// bog'liq. Agar restoran tarifi shu featureni qo'llab-quvvatlamasa, item
// menyudan butunlay yashiriladi.
const topMenuConfig = [
  { key: '/',         icon: <DashboardOutlined />,    label: 'Dashboard' },
  { key: '/orders',   icon: <ShoppingCartOutlined />, label: 'Zakazlar'  },
  { key: '/catering', icon: <GiftOutlined />,         label: 'Catering', feature: 'catering' },
  { key: '/branches', icon: <ShopOutlined />,         label: 'Filiallar' },
  { key: '/menu',     icon: <AppstoreOutlined />,     label: 'Menyu'     },
  { key: '/users',    icon: <UserOutlined />,         label: 'Mijozlar'  },
  { key: '/reviews',  icon: <StarOutlined />,         label: 'Baholar'   },
  { key: '/couriers', icon: <CarOutlined />,          label: 'Kuryerlar' },
]

const allBottomMenuItems = [
  { key: '/billing',    icon: <CreditCardOutlined />, label: 'Tariflar' },
  { key: '/settlement', icon: <CreditCardOutlined />, label: 'Moliya' },
  { key: '/admins',     icon: <TeamOutlined />,    label: 'Adminlar', superOnly: true },
  { key: '/settings',   icon: <SettingOutlined />, label: 'Sozlamalar' },
]

export default function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { admin, logout, restaurantId, currentRestaurantId, setCurrentRestaurant } = useAuthStore()
  const { branches, selectedBranchId, setBranches, selectBranch } = useBranchStore()
  const isSuper = restaurantId === null
  // Sahifalar shu rid'ni ishlatadi (restaurant admin uchun = restaurantId, super uchun = tanlangan)
  const effectiveRid = currentRestaurantId
  const bottomMenuItems = allBottomMenuItems.filter((i) => !i.superOnly || isSuper)
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [plan, setPlan] = useState(null)
  const [features, setFeatures] = useState({})
  const [allRestaurants, setAllRestaurants] = useState([])

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Super-admin uchun barcha restoranlarni yuklash (selector uchun)
  useEffect(() => {
    if (!isSuper) {
      // Restoran admin — restaurant list'ni tozalaymiz (selector ko'rinmasin)
      setAllRestaurants([])
      return
    }
    getSuperRestaurants()
      .then((r) => {
        const list = r.data || []
        setAllRestaurants(list)
        // Birinchi restoran avtomatik tanlansin (joriy yo'q bo'lsa)
        if (!effectiveRid && list.length > 0) {
          setCurrentRestaurant(list[0].id)
        }
      })
      .catch(() => setAllRestaurants([]))
  }, [isSuper])

  // Load branches (effectiveRid asosida) + IDOR validatsiya
  useEffect(() => {
    if (!effectiveRid) {
      setBranches([])
      selectBranch(null)  // restoran yo'q — branch ham yo'q
      return
    }
    getAdminBranches({ restaurant_id: effectiveRid })
      .then((r) => {
        const list = r.data || []
        setBranches(list)
        // SaaS izolatsiya: selectedBranchId joriy restoranga tegishli ekanini tekshirish
        const branchIds = list.map(b => b.id)
        if (selectedBranchId && !branchIds.includes(selectedBranchId)) {
          // Stale branch (boshqa restoraniki) — reset
          selectBranch(null)
        }
        if (!selectedBranchId && list.length === 1) selectBranch(list[0].id)
      })
      .catch(() => { setBranches([]); selectBranch(null) })
  }, [effectiveRid])

  // Load current plan + features
  useEffect(() => {
    if (!effectiveRid) {
      setPlan(null); setFeatures({})
      return
    }
    getMyPlan({ restaurant_id: effectiveRid })
      .then((r) => {
        setPlan(r.data?.plan || null)
        setFeatures(r.data?.features || {})
      })
      .catch(() => { setPlan(null); setFeatures({}) })
  }, [effectiveRid])

  // Tarif featurelariga ko'ra menu item'larni filter qilamiz. Agar restoran
  // tarifi qo'llab-quvvatlamasa, item menyudan butunlay yashiriladi (locked
  // stub qo'shilmaydi — foydalanuvchini chalg'itmaslik uchun).
  const topMenuItems = topMenuConfig.filter((item) => {
    if (!item.feature) return true
    // effectiveRid hali yuklanmagan bo'lsa, item ko'rinsin (loading flicker bo'lmasin)
    if (!effectiveRid) return true
    return !!features[item.feature]
  })

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
        {/* Super admin: restoran tanlash dropdown */}
        {isSuper && allRestaurants.length > 0 && (
          <Select
            value={effectiveRid}
            onChange={(rid) => { setCurrentRestaurant(rid); selectBranch(null) }}
            placeholder="🏪 Restoran tanlang"
            style={{ width: '100%', marginTop: 10 }}
            size="small"
            options={allRestaurants.map((r) => ({
              value: r.id, label: `${r.name}${r.status !== 'active' ? ' (' + r.status + ')' : ''}`,
            }))}
          />
        )}
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
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
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
