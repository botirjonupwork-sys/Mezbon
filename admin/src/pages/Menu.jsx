import { useEffect, useState, useRef } from 'react'
import {
  Table, Switch, Button, Tag, Modal, Form, Input,
  InputNumber, Select, Space, Card, Typography, message,
  Popconfirm, Divider, Upload, Image, Avatar, Tabs, Segmented, Row, Col
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  CheckOutlined, UploadOutlined, PictureOutlined,
  AppstoreOutlined, UnorderedListOutlined
} from '@ant-design/icons'
import {
  getCategories, getProducts, toggleStop,
  createProduct, updateProduct, deleteProduct,
  createCategory, updateCategory, deleteCategory, uploadImage, deleteImage,
  getMyPlan,
} from '../api'
import { useBranchStore } from '../store/branch'
import { useAuthStore } from '../store/auth'

const { Title } = Typography

// ── Kategoriya Select + inline qo'shish ───────────────
function CategorySelect({ value, onChange, categories, onCategoryAdded, branchId, restaurantId }) {
  const [newCatName, setNewCatName] = useState('')
  const [adding, setAdding] = useState(false)
  const [open, setOpen] = useState(false)
  const inputRef = useRef(null)

  const handleAddCategory = async () => {
    const name = newCatName.trim()
    if (!name) return
    setAdding(true)
    try {
      const catData = { name_uz: name, order: categories.length + 1 }
      if (branchId) catData.branch_id = branchId
      const qParams = restaurantId ? { restaurant_id: restaurantId } : {}
      const res = await createCategory(catData, qParams)
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

// ── Rasm tanlash komponenti (yuklamaydi — faqat ko'rsatish + File saqlash) ──
// value = { url?: string, file?: File, previewUrl?: string }
function ImageUploader({ value, onChange }) {
  const handleFile = (file) => {
    if (!file.type.startsWith('image/')) {
      message.error('Faqat rasm fayllarini yuklang')
      return false
    }
    // Local preview URL yaratish (brauzer xotirasida)
    const previewUrl = URL.createObjectURL(file)
    onChange({ file, previewUrl, url: value?.url || null })
    return false  // antd upload ni to'xtatish
  }

  const handleClear = () => {
    if (value?.previewUrl) URL.revokeObjectURL(value.previewUrl)
    onChange({ url: null, file: null, previewUrl: null })
  }

  const displayUrl = value?.previewUrl
    || (value?.url ? (value.url.startsWith('http') ? value.url : value.url) : null)
  const hasImage = !!displayUrl

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      {hasImage && (
        <Image
          src={displayUrl}
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
        <Button icon={<UploadOutlined />}>
          {hasImage ? "Rasmni almashtirish" : "Rasm tanlash"}
        </Button>
      </Upload>
      {hasImage && (
        <Button size="small" danger onClick={handleClear}>
          O'chirish
        </Button>
      )}
      {value?.file && (
        <span style={{ fontSize: 12, color: '#fa8c16' }}>
          Saqlash bosilganda yuklanadi
        </span>
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
  // imageData = { url?: string, file?: File, previewUrl?: string }
  const [imageData, setImageData] = useState({ url: null, file: null, previewUrl: null })
  const [pageSize, setPageSize] = useState(10)
  const selectedBranchId = useBranchStore((s) => s.selectedBranchId)
  const restaurantId = useAuthStore((s) => s.currentRestaurantId)

  const [activeTab, setActiveTab] = useState('menu')
  const [filterCategoryId, setFilterCategoryId] = useState(null)
  const [cateringAllowed, setCateringAllowed] = useState(false)
  const [cateringProducts, setCateringProducts] = useState([])
  const [cateringModalOpen, setCateringModalOpen] = useState(false)
  const [editingCatering, setEditingCatering] = useState(null)
  const [cateringForm] = Form.useForm()
  const [cateringFilterGroup, setCateringFilterGroup] = useState('all') // all | somsa | nan

  // Kategoriya CRUD state
  const [catModalOpen, setCatModalOpen] = useState(false)
  const [editingCategory, setEditingCategory] = useState(null)
  const [catForm] = Form.useForm()

  const fetchData = async () => {
    setLoading(true)
    try {
      const params = {}
      if (restaurantId) params.restaurant_id = restaurantId
      if (selectedBranchId) params.branch_id = selectedBranchId
      const prodParams = { ...params, product_type: 'regular' }
      if (filterCategoryId) prodParams.category_id = filterCategoryId
      const cateringParams = { ...params, product_type: 'catering' }
      const [catRes, prodRes, cateringRes] = await Promise.all([
        getCategories(params),
        getProducts(prodParams),
        getProducts(cateringParams),
      ])
      setCategories(catRes.data || [])
      setProducts(prodRes.data || [])
      setCateringProducts(cateringRes.data || [])
    } catch {
      message.error('Malumotlarni yuklashda xato')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [selectedBranchId, filterCategoryId])

  // Tarif featurelar — Catering ruxsat etilgan bo'lsagina tab ko'rsatamiz
  useEffect(() => {
    if (!restaurantId) { setCateringAllowed(false); return }
    getMyPlan({ restaurant_id: restaurantId })
      .then((r) => {
        const allowed = !!(r.data?.features?.catering)
        setCateringAllowed(allowed)
        // Agar Catering tab tanlangan, lekin tarifda yo'q — menu'ga qaytaramiz
        if (!allowed && activeTab === 'catering') setActiveTab('menu')
      })
      .catch(() => setCateringAllowed(false))
  }, [restaurantId])

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
    setImageData({ url: null, file: null, previewUrl: null })
    form.resetFields()
    setModalOpen(true)
  }

  const openEdit = (product) => {
    setEditingProduct(product)
    setHasTimeLimit(product.has_time_limit || false)
    setImageData({ url: product.image_url || null, file: null, previewUrl: null })
    form.setFieldsValue({ ...product, image_url: product.image_url })
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()

      // Rasmni faqat saqlash bosilganda yuklash
      let finalImageUrl = imageData.url
      if (imageData.file) {
        // Eski rasmni o'chirish (agar edit va yangi rasm yuklanayotgan bo'lsa)
        const oldUrl = editingProduct?.image_url
        if (oldUrl && oldUrl.startsWith('/static/')) {
          try { await deleteImage(oldUrl) } catch { /* ignore */ }
        }
        try {
          const res = await uploadImage(imageData.file)
          finalImageUrl = res.data.url
        } catch {
          message.error('Rasm yuklashda xato')
          return
        }
      } else if (editingProduct && editingProduct.image_url && !imageData.url) {
        // Rasmni o'chirish tugmasi bosilgan bo'lsa — eski rasmni o'chirish
        const oldUrl = editingProduct.image_url
        if (oldUrl.startsWith('/static/')) {
          try { await deleteImage(oldUrl) } catch { /* ignore */ }
        }
        finalImageUrl = null
      }

      const payload = { ...values, image_url: finalImageUrl }
      if (selectedBranchId) payload.branch_id = selectedBranchId
      else if (editingProduct?.branch_id) payload.branch_id = editingProduct.branch_id
      const qParams = restaurantId ? { restaurant_id: restaurantId } : {}
      if (editingProduct) {
        await updateProduct(editingProduct.id, payload, qParams)
        message.success('Yangilandi')
      } else {
        await createProduct(payload, qParams)
        message.success("Qo'shildi")
      }
      // Preview URL ni tozalash
      if (imageData.previewUrl) URL.revokeObjectURL(imageData.previewUrl)
      setModalOpen(false)
      fetchData()
    } catch (err) {
      if (err?.errorFields) return
      message.error('Saqlashda xato')
    }
  }

  const handleDelete = async (id) => {
    try {
      // Mahsulot rasmi bo'lsa — faylni ham o'chirish
      const prod = products.find((p) => p.id === id)
      if (prod?.image_url && prod.image_url.startsWith('/static/')) {
        try { await deleteImage(prod.image_url) } catch { /* ignore */ }
      }
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

  // ── Kategoriya CRUD ──────────────────────────────
  const openAddCategory = () => {
    setEditingCategory(null)
    catForm.resetFields()
    setCatModalOpen(true)
  }

  const openEditCategory = (cat) => {
    setEditingCategory(cat)
    catForm.setFieldsValue(cat)
    setCatModalOpen(true)
  }

  const handleSaveCategory = async () => {
    try {
      const values = await catForm.validateFields()
      if (editingCategory) {
        await updateCategory(editingCategory.id, values)
        message.success('Kategoriya yangilandi')
      } else {
        const catData = { ...values }
        if (selectedBranchId) catData.branch_id = selectedBranchId
        const qParams = restaurantId ? { restaurant_id: restaurantId } : {}
        await createCategory(catData, qParams)
        message.success("Kategoriya qo'shildi")
      }
      setCatModalOpen(false)
      fetchData()
    } catch (err) {
      if (err?.errorFields) return
      message.error('Saqlashda xato')
    }
  }

  const handleDeleteCategory = async (id) => {
    try {
      await deleteCategory(id)
      message.success("Kategoriya o'chirildi")
      fetchData()
    } catch {
      message.error("O'chirishda xato")
    }
  }

  // ── Catering CRUD ─────────────────────────────────
  const openAddCatering = () => {
    setEditingCatering(null)
    cateringForm.resetFields()
    cateringForm.setFieldsValue({
      catering_group: 'somsa',
      unit_price_usd: 1.2,
    })
    setCateringModalOpen(true)
  }

  const openEditCatering = (item) => {
    setEditingCatering(item)
    cateringForm.setFieldsValue(item)
    setCateringModalOpen(true)
  }

  const handleSaveCatering = async () => {
    try {
      const values = await cateringForm.validateFields()
      const payload = {
        ...values,
        product_type: 'catering',
        category_id: values.category_id || categories[0]?.id || 1,
        price: values.unit_price_usd || 1.2,
      }
      const qParams = restaurantId ? { restaurant_id: restaurantId } : {}
      if (editingCatering) {
        await updateProduct(editingCatering.id, payload, qParams)
        message.success('Yangilandi')
      } else {
        await createProduct(payload, qParams)
        message.success("Qo'shildi")
      }
      setCateringModalOpen(false)
      fetchData()
    } catch (err) {
      if (err?.errorFields) return
      message.error('Saqlashda xato')
    }
  }

  const handleDeleteCatering = async (id) => {
    try {
      await deleteProduct(id)
      message.success("O'chirildi")
      fetchData()
    } catch {
      message.error("O'chirishda xato")
    }
  }

  const GROUP_LABEL = {
    somsa: '🥟 Somsa',
    nan: '🍞 Non',
  }

  const cateringColumns = [
    { title: '#', dataIndex: 'id', width: 60 },
    { title: 'Nomi', dataIndex: 'name_uz' },
    {
      title: 'Guruh', dataIndex: 'catering_group', width: 100,
      render: (v) => v ? <Tag color={v === 'somsa' ? 'orange' : 'gold'}>{GROUP_LABEL[v] || v}</Tag> : '—',
    },
    {
      title: '1 dona ($)', dataIndex: 'unit_price_usd', width: 110,
      render: (v) => v ? `$${v}` : '—',
    },
    {
      title: '1 dona saboy (som)', dataIndex: 'unit_price_pickup_uzs', width: 160,
      render: (v) => v ? `${v.toLocaleString()} som` : '—',
    },
    {
      title: 'Amallar', width: 100,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditCatering(record)} />
          <Popconfirm
            title="O'chirilsinmi?"
            onConfirm={() => handleDeleteCatering(record.id)}
            okText="Ha" cancelText="Yo'q"
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    },
  ]

  const categoryColumns = [
    { title: '#', dataIndex: 'id', width: 60 },
    { title: 'Nomi', dataIndex: 'name_uz' },
    { title: 'Tartib', dataIndex: 'order', width: 80 },
    {
      title: 'Tur', width: 140,
      render: (_, r) => r.branch_id
        ? <Tag color="blue">Filial</Tag>
        : <Tag color="green">Restaurant</Tag>
    },
    {
      title: 'Amallar', width: 120,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditCategory(record)} />
          <Popconfirm
            title="O'chirilsinmi?"
            onConfirm={() => handleDeleteCategory(record.id)}
            okText="Ha" cancelText="Yo'q"
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    },
  ]

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

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        type="card"
        style={{ marginBottom: 16 }}
        items={[
          {
            key: 'menu',
            label: <span><AppstoreOutlined /> Menyu</span>,
            children: (
              <Card
                extra={
                  <Space>
                    <Select
                      allowClear
                      placeholder="Kategoriya bo'yicha filter"
                      value={filterCategoryId}
                      onChange={setFilterCategoryId}
                      options={categories.map((c) => ({ value: c.id, label: c.name_uz }))}
                      style={{ minWidth: 220 }}
                    />
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={openAdd}
                      style={{ background: '#fa8c16', borderColor: '#fa8c16' }}
                    >
                      Mahsulot qo'shish
                    </Button>
                  </Space>
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
            ),
          },
          {
            key: 'categories',
            label: <span><UnorderedListOutlined /> Kategoriyalar</span>,
            children: (
              <Card
                extra={
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={openAddCategory}
                    style={{ background: '#fa8c16', borderColor: '#fa8c16' }}
                  >
                    Kategoriya qo'shish
                  </Button>
                }
              >
                <Table
                  dataSource={categories}
                  columns={categoryColumns}
                  rowKey="id"
                  loading={loading}
                  pagination={false}
                  scroll={{ x: 500 }}
                />
              </Card>
            ),
          },
          cateringAllowed && {
            key: 'catering',
            label: <span>🎉 Catering</span>,
            children: (
              <div>
                {/* Mahsulotlar jadvali */}
                <Card
                  title="🍽 Catering mahsulotlari"
                  extra={
                    <Space>
                      <Segmented
                        value={cateringFilterGroup}
                        onChange={setCateringFilterGroup}
                        options={[
                          { label: 'Barchasi', value: 'all' },
                          { label: '🥟 Somsa', value: 'somsa' },
                          { label: '🍞 Non', value: 'nan' },
                        ]}
                      />
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={openAddCatering}
                        style={{ background: '#fa8c16', borderColor: '#fa8c16' }}
                      >
                        Mahsulot qo'shish
                      </Button>
                    </Space>
                  }
                >
                  <Table
                    dataSource={cateringFilterGroup === 'all'
                      ? cateringProducts
                      : cateringProducts.filter((p) => p.catering_group === cateringFilterGroup)}
                    columns={cateringColumns}
                    rowKey="id"
                    loading={loading}
                    pagination={false}
                    scroll={{ x: 800 }}
                  />
                </Card>
              </div>
            ),
          },
        ].filter(Boolean)}
      />

      {/* ── Catering modal ── */}
      <Modal
        title={editingCatering ? 'Catering mahsulotni tahrirlash' : 'Yangi catering mahsulot'}
        open={cateringModalOpen}
        onOk={handleSaveCatering}
        onCancel={() => setCateringModalOpen(false)}
        okText="Saqlash"
        cancelText="Bekor"
        width={560}
        okButtonProps={{ style: { background: '#fa8c16', borderColor: '#fa8c16' } }}
      >
        <Form form={cateringForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="catering_group"
            label="Guruh"
            rules={[{ required: true, message: 'Guruhni tanlang' }]}
            extra="Somsa va Non guruhlari alohida minimal miqdorga ega"
          >
            <Select
              options={[
                { value: 'somsa', label: '🥟 Somsa guruhi' },
                { value: 'nan', label: '🍞 Non guruhi' },
              ]}
            />
          </Form.Item>

          <Form.Item name="name_uz" label="Nomi (UZ)" rules={[{ required: true, message: 'Nomini kiriting' }]}>
            <Input placeholder="Go'shtli somsa / Shirmoy non" />
          </Form.Item>
          <Form.Item name="name_ru" label="Nomi (RU)">
            <Input placeholder="Samsa s myasom / Shirmoy nan" />
          </Form.Item>
          <Form.Item name="description_uz" label="Tavsif">
            <Input.TextArea rows={2} placeholder="Qisqacha ma'lumot" />
          </Form.Item>
          <Form.Item name="category_id" label="Kategoriya" rules={[{ required: true, message: 'Kategoriya tanlang' }]}>
            <Select
              options={categories.map((c) => ({ value: c.id, label: c.name_uz }))}
              placeholder="Kategoriya"
            />
          </Form.Item>

          <Form.Item
            name="unit_price_usd"
            label="1 dona narxi ($)"
            rules={[{ required: true, message: 'Narx kiriting' }]}
            extra="Joyiga borib yopish va dastavka uchun ishlatiladi (USD kursida)"
          >
            <InputNumber min={0} style={{ width: '100%' }} step={0.1} placeholder="1.2" />
          </Form.Item>

          <Form.Item
            name="unit_price_pickup_uzs"
            label="1 dona saboy (olib ketish) narxi (so'm)"
            extra="Saboy tanlanganda ishlatiladi (so'mda, arzonroq bo'lishi mumkin)"
          >
            <InputNumber
              min={0}
              style={{ width: '100%' }}
              step={1000}
              formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
              parser={(v) => v.replace(/,/g, '')}
              placeholder="10000"
            />
          </Form.Item>

          <Form.Item label="Rasm">
            <ImageUploader value={imageData} onChange={setImageData} />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Kategoriya modal ── */}
      <Modal
        title={editingCategory ? 'Kategoriyani tahrirlash' : 'Yangi kategoriya'}
        open={catModalOpen}
        onOk={handleSaveCategory}
        onCancel={() => setCatModalOpen(false)}
        okText="Saqlash"
        cancelText="Bekor"
        okButtonProps={{ style: { background: '#fa8c16', borderColor: '#fa8c16' } }}
      >
        <Form form={catForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name_uz" label="Nomi (UZ)" rules={[{ required: true, message: 'Nomini kiriting' }]}>
            <Input placeholder="Somsalar" />
          </Form.Item>
          <Form.Item name="name_ru" label="Nomi (RU)">
            <Input placeholder="Самсы" />
          </Form.Item>
          <Form.Item name="order" label="Tartib raqami">
            <InputNumber min={0} style={{ width: '100%' }} placeholder="1" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingProduct ? 'Mahsulotni tahrirlash' : 'Yangi mahsulot'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => {
          if (imageData.previewUrl) URL.revokeObjectURL(imageData.previewUrl)
          setModalOpen(false)
        }}
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
              branchId={selectedBranchId}
              restaurantId={restaurantId}
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

          {/* Rasm yuklash — Saqlash bosilganda yuklanadi */}
          <Form.Item label="Mahsulot rasmi">
            <ImageUploader value={imageData} onChange={setImageData} />
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
