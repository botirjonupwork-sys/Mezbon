import { useNavigate } from 'react-router-dom'
import { Card, Row, Col, Typography, Tag, Badge } from 'antd'
import {
  ShopOutlined, CreditCardOutlined, CarOutlined,
  RobotOutlined, GiftOutlined, UserOutlined,
  RightOutlined, LockOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '../../store/auth'
import { useBranchStore } from '../../store/branch'
import { useEffect, useState } from 'react'
import { getMyPlan } from '../../api'

const { Title, Text } = Typography

const settingsCards = [
  {
    key: 'restaurant',
    path: '/settings/restaurant',
    icon: <ShopOutlined style={{ fontSize: 28 }} />,
    title: 'Restoran',
    description: "Nomi, manzil, telefon, xarita, ish vaqti",
    color: '#fa8c16',
  },
  {
    key: 'payments',
    path: '/settings/payments',
    icon: <CreditCardOutlined style={{ fontSize: 28 }} />,
    title: "To'lovlar",
    description: "Click, Payme, Telegram Pay, QQS",
    color: '#52c41a',
  },
  {
    key: 'delivery',
    path: '/settings/delivery',
    icon: <CarOutlined style={{ fontSize: 28 }} />,
    title: 'Yetkazish',
    description: "O'z kuryer, Yandex Delivery",
    color: '#1890ff',
  },
  {
    key: 'bots',
    path: '/settings/bots',
    icon: <RobotOutlined style={{ fontSize: 28 }} />,
    title: 'Telegram Botlar',
    description: "Mijoz bot, Kuryer bot tokenlari",
    color: '#722ed1',
  },
  {
    key: 'catering',
    path: '/settings/catering',
    icon: <GiftOutlined style={{ fontSize: 28 }} />,
    title: 'Catering',
    description: "Miqdorlar, narxlar, bildirishnoma",
    color: '#eb2f96',
    feature: 'catering',
  },
  {
    key: 'profile',
    path: '/settings/profile',
    icon: <UserOutlined style={{ fontSize: 28 }} />,
    title: 'Profil',
    description: "Login, parol o'zgartirish",
    color: '#13c2c2',
  },
]

export default function SettingsIndex() {
  const navigate = useNavigate()
  const { currentRestaurantId: restaurantId } = useAuthStore()
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
  const [features, setFeatures] = useState({})
  const [plan, setPlan] = useState(null)

  useEffect(() => {
    if (!restaurantId) return
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

  const handleCardClick = (card) => {
    // Check if feature is locked
    if (card.feature && !features[card.feature]) {
      return // Don't navigate if locked
    }
    navigate(card.path)
  }

  const isLocked = (card) => {
    return card.feature && !features[card.feature]
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <div style={{ marginBottom: 32 }}>
        <Title level={3} style={{ marginBottom: 8 }}>
          Sozlamalar
        </Title>
        <Text type="secondary">
          Restoran sozlamalarini boshqaring
        </Text>
        {selectedBranchId && (
          <Tag color="blue" style={{ marginLeft: 12 }}>
            Filial rejimi
          </Tag>
        )}
      </div>

      <Row gutter={[16, 16]}>
        {settingsCards.map((card) => {
          const locked = isLocked(card)

          return (
            <Col xs={24} sm={12} lg={8} key={card.key}>
              <Card
                hoverable={!locked}
                onClick={() => handleCardClick(card)}
                style={{
                  height: '100%',
                  cursor: locked ? 'not-allowed' : 'pointer',
                  opacity: locked ? 0.6 : 1,
                  borderRadius: 12,
                  border: '1px solid #f0f0f0',
                  transition: 'all 0.3s ease',
                }}
                styles={{
                  body: { padding: 20 }
                }}
                className="settings-card"
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                  <div
                    style={{
                      width: 52,
                      height: 52,
                      borderRadius: 12,
                      background: `${card.color}15`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: card.color,
                      marginBottom: 16,
                    }}
                  >
                    {card.icon}
                  </div>
                  {locked ? (
                    <Tag icon={<LockOutlined />} color="default">
                      Pro
                    </Tag>
                  ) : (
                    <RightOutlined style={{ color: '#bfbfbf', fontSize: 14 }} />
                  )}
                </div>

                <Title level={5} style={{ marginBottom: 4, marginTop: 0 }}>
                  {card.title}
                </Title>
                <Text type="secondary" style={{ fontSize: 13 }}>
                  {card.description}
                </Text>
              </Card>
            </Col>
          )
        })}
      </Row>

      <style>{`
        .settings-card:hover {
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
          transform: translateY(-2px);
        }
      `}</style>
    </div>
  )
}
