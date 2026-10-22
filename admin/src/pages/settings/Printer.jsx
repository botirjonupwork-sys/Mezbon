import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Input, Button, Typography, message, Spin,
  Radio, InputNumber, Alert, Tag, Space, Select, Divider, Empty,
} from 'antd'
import {
  ArrowLeftOutlined, SaveOutlined, PrinterOutlined, ApiOutlined,
  PlusOutlined, DeleteOutlined,
} from '@ant-design/icons'
import { getPosConfig, updatePosConfig, posTestPrint, getCategories } from '../../api'
import { useAuthStore } from '../../store/auth'

const { Title, Text, Paragraph } = Typography

const cardStyle = { marginBottom: 12, borderRadius: 14, border: '1px solid #ececec', boxShadow: 'none' }

const emptyPrinter = () => ({ name: '', ip: '', port: 9100, paper_width: 80, category_ids: [], is_default: false })

export default function PrinterSettings() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [terminals, setTerminals] = useState(0)
  const [enabled, setEnabled] = useState(false)
  const [printers, setPrinters] = useState([])
  const [categories, setCategories] = useState([])

  const { currentRestaurantId: restaurantId } = useAuthStore()
  const restParams = restaurantId ? { restaurant_id: restaurantId } : {}

  const load = () => {
    if (!restaurantId) { setLoading(false); return }
    setLoading(true)
    Promise.all([getPosConfig(restParams), getCategories(restParams)])
      .then(([cfgR, catR]) => {
        const d = cfgR.data || {}
        const cfg = d.pos_config || {}
        setEnabled((d.pos_system_type || 'NONE') === 'LAN_PRINTER')
        setTerminals(d.connected_terminals || 0)
        setCategories((catR.data || []).map((c) => ({ value: c.id, label: c.name_uz || c.name || `#${c.id}` })))
        let list = Array.isArray(cfg.printers) ? cfg.printers : []
        // Eski yagona printer bo'lsa — ro'yxatga ko'chiramiz
        if (list.length === 0 && cfg.printer_ip) {
          list = [{ name: 'Asosiy', ip: cfg.printer_ip, port: cfg.printer_port || 9100, paper_width: cfg.paper_width || 80, category_ids: [], is_default: true }]
        }
        if (list.length && !list.some((p) => p.is_default)) list[0].is_default = true
        setPrinters(list.map((p) => ({ ...emptyPrinter(), ...p })))
      })
      .catch(() => message.error('Sozlamalarni yuklab bo‘lmadi'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [restaurantId])

  const upd = (i, field, val) => setPrinters((ps) => ps.map((p, idx) => idx === i ? { ...p, [field]: val } : p))
  const setDefault = (i) => setPrinters((ps) => ps.map((p, idx) => ({ ...p, is_default: idx === i })))
  const addPrinter = () => setPrinters((ps) => [...ps, { ...emptyPrinter(), is_default: ps.length === 0 }])
  const removePrinter = (i) => setPrinters((ps) => {
    const next = ps.filter((_, idx) => idx !== i)
    if (next.length && !next.some((p) => p.is_default)) next[0].is_default = true
    return next
  })

  const save = async (turnOn) => {
    if (turnOn) {
      for (const p of printers) {
        if (!p.name.trim() || !p.ip.trim()) {
          message.warning('Har printerга nom va IP manzil kiriting')
          return
        }
      }
      if (printers.length && !printers.some((p) => p.is_default)) {
        message.warning('Bitta printerни "asosiy" deb belgilang')
        return
      }
    }
    setSaving(true)
    try {
      await updatePosConfig({
        pos_system_type: turnOn ? 'LAN_PRINTER' : 'NONE',
        pos_config: {
          printers: printers.map((p) => ({
            name: p.name.trim(), ip: p.ip.trim(), port: Number(p.port) || 9100,
            paper_width: Number(p.paper_width) || 80,
            category_ids: p.category_ids || [], is_default: !!p.is_default,
          })),
        },
      }, restParams)
      setEnabled(turnOn)
      message.success('Saqlandi')
    } catch (e) {
      message.error('Saqlashda xatolik')
    } finally {
      setSaving(false)
    }
  }

  const test = async () => {
    setTesting(true)
    try {
      const r = await posTestPrint(restParams)
      const res = r.data?.result || {}
      if (r.data?.ok) message.success('Test chek(lar) yuborildi ✅')
      else if (res.error === 'no_agent' || res.delivered === 0) message.warning('Agent ulanmagan — kassa kompyuterida agent dasturi ishlab turishi kerak')
      else if (res.error === 'not_configured') message.warning('Avval printer qo‘shing va saqlang')
      else message.error('Test chek yuborilmadi')
      load()
    } catch (e) {
      message.error('Test chek xatosi')
    } finally {
      setTesting(false)
    }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>

  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }}>
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/settings')} style={{ marginBottom: 12 }}>
        Sozlamalar
      </Button>

      <Title level={3} style={{ marginTop: 0, marginBottom: 4 }}>
        <PrinterOutlined /> Chek printerlari (stansiyalar)
      </Title>
      <Text type="secondary">Har stansiyaga (somsa, mangal, oshxona, ichimlik...) o‘z printeri — kategoriya bo‘yicha avtomatik bo‘linadi</Text>

      <Space style={{ margin: '16px 0' }}>
        <Text strong>Holat:</Text>
        {enabled ? <Tag color="green">Yoqilgan</Tag> : <Tag>O‘chirilgan</Tag>}
        <Text strong style={{ marginLeft: 12 }}>Agent:</Text>
        {terminals > 0 ? <Tag color="green" icon={<ApiOutlined />}>{terminals} ta ulangan</Tag> : <Tag color="orange" icon={<ApiOutlined />}>ulanmagan</Tag>}
      </Space>

      {printers.length === 0 && (
        <Card style={cardStyle} styles={{ body: { padding: 24 } }}>
          <Empty description="Hali printer qo‘shilmagan" />
        </Card>
      )}

      {printers.map((p, i) => (
        <Card key={i} style={cardStyle} styles={{ body: { padding: 20 } }}
          title={<Space>{p.name || `Printer ${i + 1}`} {p.is_default && <Tag color="blue">asosiy</Tag>}</Space>}
          extra={<Button danger size="small" icon={<DeleteOutlined />} onClick={() => removePrinter(i)}>O‘chirish</Button>}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>Stansiya nomi</Text>
              <Input placeholder="Mangal" value={p.name} onChange={(e) => upd(i, 'name', e.target.value)} />
            </div>
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>Printer IP</Text>
              <Input placeholder="192.168.1.50" value={p.ip} onChange={(e) => upd(i, 'ip', e.target.value)} />
            </div>
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>Port</Text>
              <InputNumber min={1} max={65535} style={{ width: '100%' }} value={p.port} onChange={(v) => upd(i, 'port', v)} />
            </div>
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>Qog‘oz eni</Text>
              <Radio.Group value={p.paper_width} onChange={(e) => upd(i, 'paper_width', e.target.value)}>
                <Radio.Button value={80}>80mm</Radio.Button>
                <Radio.Button value={58}>58mm</Radio.Button>
              </Radio.Group>
            </div>
          </div>
          <div style={{ marginTop: 12 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>Bu printerga chiqadigan kategoriyalar</Text>
            <Select mode="multiple" allowClear style={{ width: '100%' }} placeholder="Kategoriyalarni tanlang"
              value={p.category_ids} onChange={(v) => upd(i, 'category_ids', v)} options={categories}
              optionFilterProp="label" />
          </div>
          <div style={{ marginTop: 12 }}>
            <Radio checked={p.is_default} onChange={() => setDefault(i)}>
              Asosiy printer (barcha cheklar shu yerdan chiqadi)
            </Radio>
          </div>
        </Card>
      ))}

      <Button type="dashed" icon={<PlusOutlined />} onClick={addPrinter} block style={{ marginBottom: 16 }}>
        Printer qo‘shish
      </Button>

      <Space wrap>
        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => save(true)} disabled={printers.length === 0}>
          Saqlash va yoqish
        </Button>
        <Button icon={<PrinterOutlined />} loading={testing} onClick={test}>Test chek (hammasiga)</Button>
        {enabled && <Button danger onClick={() => save(false)} loading={saving}>O‘chirish</Button>}
      </Space>

      <Alert type="info" showIcon style={{ borderRadius: 12, marginTop: 16 }}
        message="Qanday ishlaydi"
        description={
          <Paragraph style={{ marginBottom: 0 }}>
            <b>Asosiy printer</b>ga har doim to‘liq mijoz cheki chiqadi — kategoriya biriktirilmasa ham.
            Qo‘shimcha stansiyalarga faqat tanlangan kategoriyadagi mahsulotlar uchun qisqa oshxona cheki ketadi.
            <br />
            Server printerга to‘g‘ridan ula olmaydi: kassa kompyuteriда <b>agent dasturi</b> (tools/xprinter_agent.py)
            ishlab turishi shart. Chek to‘lov tasdiqlanganda (yoki naqd zakazda) avtomatik chiqadi.
          </Paragraph>
        }
      />
    </div>
  )
}
