import { useEffect, useState, useRef } from 'react'
import {
  Table, Switch, Button, Tag, Modal, Form, Input,
  InputNumber, Select, Space, Card, Typography, message,
  Popconfirm, Divider, Upload, Image, Avatar
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  CheckOutlined, UploadOutlined, PictureOutlined
} from '@ant-design/icons'
import {
  getCategories, getProducts, toggleStop,
  createProduct, updateProduct, deleteProduct,
  createCategory, uploadImage
} from '../api'

const { Title } = Typography

// ── Kategoriya Select + inline qo'shish ───────────────
function CategorySelect({ value, onChange, categories, onCategoryAdded }) {
  const [newCatName, setNewCatName] = useState('')
  const [adding, setAdding] = useState(false)
  const [open, setOpen] = useState(false)
  const inputRef = useRef(null)

  const handleAddCategory = async () => {
    const name = newCatName.trim()
    if (!name) return
    setAdding(true)
    try {
      const res = await createCategory({ name_uz: name, order: categories.length + 1 })
      const newCat = res.data
      message.success(`"${name}" kategoriyasi qo'shildi`)
      setNewCatName('')
      onCategoryAdded(newCat)
      onChange(newCat.id)
      setOpen(false)
    } catch {
      message.error("Kategoriya qo'shishda xato")
    } finally {
      setAdding(false)
    }
  }

  const dropdownRender = (menu) => (
    <>
      {menu}
      <Divider style={{ margin: '8px 0' }} />
      <Space style={{ padding: '4px 8px', width: '100%' }}>
        <Input
          ref={inputRef}
          size="small"
          placeholder="Yangi kategoriya nomi..."
          value={newCatName}
          onChange={(e) => setNewCatName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAddCategory()}
          style={{ flex: 1 }}
        />
        <Button
          size="small"
          type="primary"
          icon={<CheckOutlined />}
          loading={adding}
          onClick={handleAddCategory}
          disabled={!newCatName.trim()}
          style={{ background: '#fa8c16', borderColor: '#fa8c16' }}
        >
          Qo'shish
        </Button>
      </Space>
    </>
  )

  return (
    <Select
      value={value}
      onChange={onChange}
      open={open}
      onDropdownVisibleChange={setOpen}
      options={categories.map((c) => ({ value: c.id, label: c.name_uz }))}
      dropdownRender={dropdownRender}
      placeholder="Kategoriya tanlang..."
      style={{ width: '100%' }}
    />
  )
}

// ── Rasm yuklash komponenti ───────────────────────────
function ImageUploader({ value, onChange }) {
  const [uploading, setUploading] = useState(false)

  const handleFile = async (file) => {
    // Faqat rasm fayllari
    if (!file.type.startsWith('image/')) {
      message.error('Faqat rasm fayllarini yuklang')
      return false
    }
    setUploading(true)
    try {
      const res = await uploadImage(file)
      const url = res.data.url
      onChange(url)
      message.success("Rasm yuklandi")
    } catch {
      message.error("Rasm yuklashda xato")
    } finally {
      setUploading(false)
    }
    return false // antd Upload boshqaruvini oldini olamiz
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      {value && (
        <Image
          src={value.startsWith('http') ? value : `http://localhost:8000${value}`}
          width={80}
          height={80}
          style={{ objectFit: 'cover', borderRadius: 8, border: '1px solid #f0f0f0' }}
          fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFAAAABQCAMAAAC5zwKfAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAA9QTFRFzMzM////AAAA3d3d7e3tpA1nawAAABNJREFUeNpiYGBg+D8qSBcABBgACx8B/tFs0AEAAAAASUVORK5CYII="
        />
      )}
      <Upload
        beforeUpload={handleFile}
        showUploadList={false}
        accept="image/*"
      >
        <Button
          icon={<UploadOutlined />}
          loading={uploading}
        >
          {value ? "Rasmni almashtirish" : "Rasm yuklash"}
        </Button>
      </Upload>
      {value && (
        <Button
          size="small"
          danger
          onClick={() => onChange(null)}
        >
          O'chirish
        </Button>
      )}
    </div>
  )
}

// ── Asosiy komponent ─────────────────────────────────
export default function Menu() {
  const [products, setProducts] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingProduct, setEditingProduct] = useState(null)
  const [form] = Form.useForm()
  const [hasTimeLimit, setHasTimeLimit] = useState(false)
  const [imageUrl, setImageUrl] = useState(null)
  const [pageSize, setPageSize] = useState(10)

  const fetchData = async () => {
    setLoading(true)
    try {
      const [catRes, prodRes] = await Promise.all([getCategories(), getProducts()])
      setCategories(catRes.data || [])
      setProducts(prodRes.data || [])
    } catch {
      message.error('Malumotlarni yuklashda xato')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const handleToggleStop = async (id, checked) => {
    try {
      await toggleStop(id, !checked)
      setProducts((prev) =>
        prev.map((p) => p.id === id ? { ...p, is_stop: !checked } : p)
      )
      message.success(checked ? 'Mahsulot faollashtirildi' : "Stop ga qo'yildi")
    } catch {
      message.error('Xato yuz berdi')
    }
  }

  const openAdd = () => {
    setEditingProduct(null)
    setHasTimeLimit(false)
    setImageUrl(null)
    form.resetFields()
    setModalOpen(true)
  }

  const openEdit = (product) => {
    setEditingProduct(product)
    setHasTimeLimit(product.has_time_limit || false)
    setImageUrl(product.image_url || null)
    form.setFieldsValue({ ...product, image_url: product.image_url })
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const payload = { ...values, image_url: imageUrl }
      if (editingProduct) {
        await updateProduct(editingProduct.id, payload)
        message.success('Yangilandi')
      } else {
        await createProduct(payload)
        message.success("Qo'shildi")
      }
      setModalOpen(false)
      fetchData()
    } catch (err) {
      if (err?.errorFields) return
      message.error('Saqlashda xato')
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteProduct(id)
      message.success("O'chirildi")
      fetchData()
    } catch {
      message.error("O'chirishda xato")
    }
  }

  const handleCategoryAdded = (newCat) => {
    setCategories((prev) => [...prev, newCat])
  }

  const columns = [
    {
      title: 'Rasm', dataIndex: 'image_url', width: 70,
      render: (url) => url
        ? <Image
            src={url.startsWith('http') ? url : url}
            width={50} height={50}
            style={{ objectFit: 'cover', borderRadius: 6 }}
            fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
          />
        : <Avatar icon={<PictureOutlined />} shape="square" size={50} style={{ background: '#f0f0f0', color: '#aaa' }} />
    },
    { title: 'Nomi', dataIndex: 'name_uz', width: 200 },
    {
      title: 'Kategoriya', dataIndex: 'category_id',
      render: (id) => categories.find((c) => c.id === id)?.name_uz || '—'
    },
    {
      title: 'Narx', dataIndex: 'price',
      render: (v) => `${(v || 0).toLocaleString()} so'm`
    },
    {
      title: 'Vaqt limiti', dataIndex: 'has_time_limit',
      render: (v, r) => v
        ? <Tag color="orange">⏰ {r.available_from}–{r.available_until}</Tag>
        : <Tag color="green">Doim</Tag>
    },
    {
      title: 'Stop / Faol', dataIndex: 'is_stop',
      render: (isStop, record) => (
        <Switch
          checked={!isStop}
          checkedChildren="Faol"
          unCheckedChildren="Stop"
          onChange={(checked) => handleToggleStop(record.id, checked)}
        />
      )
    },
    {
      title: 'Amallar', width: 100,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          <Popconfirm
            title="O'chirilsinmi?"
            onConfirm={() => handleDelete(record.id)}
            okText="Ha" cancelText="Yo'q"
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>Menyu Boshqaruvi</Title>

      <Card
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={openAdd}
            style={{ background: '#fa8c16', borderColor: '#fa8c16' }}
          >
            Mahsulot qo'shish
          </Button>
        }
      >
        <Table
          dataSource={products}
          columns={columns}
          rowKey="id"
          loading={loading}
          scroll={{ x: 800 }}
          pagination={{
            pageSize,
            pageSizeOptions: ['10', '30', '50'],
            showSizeChanger: true,
            onShowSizeChange: (_, size) => setPageSize(size),
            showTotal: (total) => `Jami: ${total} ta`,
          }}
        />
      </Card>

      <Modal
        title={editingProduct ? 'Mahsulotni tahrirlash' : 'Yangi mahsulot'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        okText="Saqlash"
        cancelText="Bekor"
        width={560}
        okButtonProps={{ style: { background: '#fa8c16', borderColor: '#fa8c16' } }}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name_uz" label="Nomi (UZ)" rules={[{ required: true, message: 'Nomini kiriting' }]}>
            <Input placeholder="Go'shtli somsa" />
          </Form.Item>

          <Form.Item name="name_ru" label="Nomi (RU)">
            <Input placeholder="Самса с мясом" />
          </Form.Item>

          <Form.Item
            name="category_id"
            label="Kategoriya"
            rules={[{ required: true, message: 'Kategoriya tanlang' }]}
          >
            <CategorySelect
              categories={categories}
              onCategoryAdded={handleCategoryAdded}
              value={form.getFieldValue('category_id')}
              onChange={(val) => form.setFieldValue('category_id', val)}
            />
          </Form.Item>

          <Form.Item name="price" label="Narx (so'm)" rules={[{ required: true, message: 'Narxni kiriting' }]}>
            <InputNumber
              style={{ width: '100%' }}
              min={0} step={500}
              formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
              parser={(v) => v.replace(/,/g, '')}
              placeholder="5000"
            />
          </Form.Item>

          <Form.Item name="description_uz" label="Tavsif">
            <Input.TextArea rows={2} placeholder="Mahsulot haqida qisqacha..." />
          </Form.Item>

          {/* Rasm yuklash */}
          <Form.Item label="Mahsulot rasmi">
            <ImageUploader value={imageUrl} onChange={setImageUrl} />
            <div style={{ fontSize: 12, color: '#999', marginTop: 6 }}>
              Rasm Telegram botda ham ko'rinadi
            </div>
          </Form.Item>

          <Form.Item
            name="has_time_limit"
            label="Vaqt limiti bormi?"
            valuePropName="checked"
          >
            <Switch onChange={setHasTimeLimit} />
          </Form.Item>

          {hasTimeLimit && (
            <Space align="start">
              <Form.Item name="available_from" label="Dan" rules={[{ required: true, message: 'Kiriting' }]}>
                <Input placeholder="09:00" style={{ width: 100 }} />
              </Form.Item>
              <Form.Item name="available_until" label="Gacha" rules={[{ required: true, message: 'Kiriting' }]}>
                <Input placeholder="22:00" style={{ width: 100 }} />
              </Form.Item>
            </Space>
          )}
        </Form>
      </Modal>
    </div>
  )
}
