import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import {
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useParams,
} from 'react-router-dom'
import {
  formatPrice,
  getChatHistory,
  getCurrentUser,
  getImageUrl,
  getProduct,
  getProducts,
  loginAccount,
  logoutAccount,
  registerAccount,
  sendChatMessage,
  type AuthUser,
  type ChatPageContext,
  type Product,
  type ProductMatch,
} from './api'
import { sortProducts, type ProductSortOrder } from './productSorting'

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

function Header({ account, onLogout }: { account: AuthUser | null; onLogout: () => void }) {
  return (
    <>
      <div className="announcement">OFFICIALLY LICENSED YALE MERCHANDISE <span>•</span> A CAMPUS CUSTOMS SHOP</div>
      <header className="site-header">
        <Link to="/" className="wordmark" aria-label="Campus Customs home">
          <span className="wordmark-monogram" aria-hidden="true">CC</span>
          <span className="wordmark-copy"><strong>Campus Customs</strong><small>YALE BULLDOG BLUE</small></span>
        </Link>
        <nav className="main-nav" aria-label="Main navigation">
          <NavLink to="/" end>Home</NavLink>
          <NavLink to="/products">Products</NavLink>
          <NavLink to="/about">About Us</NavLink>
        </nav>
        <div className="account-nav">
          {account ? <><span className="account-greeting">Hi, {account.first_name}</span><button className="logout-button" onClick={onLogout}>Log out</button></> : <><NavLink to="/login" className="login-link">Log in</NavLink><NavLink to="/create-account" className="account-button">Create account</NavLink></>}
        </div>
      </header>
    </>
  )
}

function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-main">
        <div>
          <div className="footer-mark">Campus Customs</div>
          <p>Yale apparel for the places, teams, and people that make campus yours.</p>
        </div>
        <div className="footer-links">
          <Link to="/products">Shop products</Link>
          <Link to="/about">About Campus Customs</Link>
          <Link to="/login">Your account</Link>
        </div>
      </div>
      <div className="footer-bottom"><span>YALE BULLDOG BLUE</span><span>New Haven, Connecticut · Campus Customs</span></div>
    </footer>
  )
}

function pageContextForPath(pathname: string): ChatPageContext {
  const productRoute = pathname.match(/^\/products\/([^/]+)\/?$/)
  const pageType: ChatPageContext['page_type'] = productRoute
    ? 'product_detail'
    : pathname === '/' ? 'home'
      : pathname === '/products' ? 'products'
        : pathname === '/about' ? 'about'
          : pathname === '/login' ? 'login'
            : pathname === '/create-account' ? 'create_account' : 'other'
  let productId: string | undefined
  if (productRoute) {
    try { productId = decodeURIComponent(productRoute[1]) } catch { productId = productRoute[1] }
  }
  return { page_type: pageType, path: pathname, ...(productId ? { product_id: productId } : {}) }
}

function ChatPanel({ account, authLoading }: { account: AuthUser | null; authLoading: boolean }) {
  const [isOpen, setIsOpen] = useState(false)
  const location = useLocation()
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string; products?: ProductMatch[] }>>([
    { role: 'assistant', content: 'Welcome to Campus Customs. Ask me about a product, price, size, or what is in stock.' },
  ])
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [error, setError] = useState('')
  const latestMessageRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (authLoading) return
    let active = true
    setHistoryLoading(true)
    setError('')
    getChatHistory()
      .then((history) => {
        if (!active) return
        if (account && history.authenticated) {
          setMessages(history.messages.length ? history.messages : [
            { role: 'assistant', content: 'Welcome to Campus Customs. Ask me about a product, price, size, or what is in stock.' },
          ])
        } else {
          setMessages([{ role: 'assistant', content: 'Welcome to Campus Customs. Ask me about a product, price, size, or what is in stock.' }])
        }
      })
      .catch(() => {
        if (active) {
          setMessages([{ role: 'assistant', content: 'Welcome to Campus Customs. Ask me about a product, price, size, or what is in stock.' }])
          setError(account ? 'Saved chat history could not be loaded.' : '')
        }
      })
      .finally(() => { if (active) setHistoryLoading(false) })
    return () => { active = false }
  }, [account?.id, authLoading])

  useEffect(() => {
    latestMessageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, pending, error])

  async function sendMessage(messageText: string) {
    const message = messageText.trim()
    if (!message || pending) return
    const history = messages.slice(-12).map(({ role, content }) => ({ role, content }))
    setMessages((current) => [...current, { role: 'user', content: message }])
    setDraft('')
    setPending(true)
    setError('')
    try {
      const answer = await sendChatMessage(message, history, pageContextForPath(location.pathname))
      setMessages((current) => [...current, { role: 'assistant', content: answer.reply, products: answer.products }])
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The shop assistant is unavailable. Please try again.')
    } finally {
      setPending(false)
    }
  }

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await sendMessage(draft)
  }

  const productRoute = location.pathname.match(/^\/products\/([^/]+)\/?$/)
  const suggestions = productRoute
    ? ['Check sizes on this item', 'What colors does it come in?', 'Find something similar']
    : ['Find hoodies', 'Show the lowest-priced items', 'What is in stock in size M?']

  return (
    <div className="chat-widget">
      {isOpen && (
        <section className="chat-window" aria-label="Campus Customs shop assistant">
          <div className="chat-heading">
            <span className="chat-avatar">CC</span>
            <div className="chat-heading-copy"><strong>Campus Customs</strong><small><i className="chat-online" /> CAMPUS SHOP ASSISTANT</small></div>
            <button className="chat-close" onClick={() => setIsOpen(false)} aria-label="Close chat">×</button>
          </div>
          <div className="chat-feed" aria-live="polite">
            {messages.map((message, index) => (
              <div className={`chat-entry chat-entry-${message.role}`} key={`${message.role}-${index}`}>
                <div className="chat-message">{message.content}</div>
                {message.products?.length ? <div className="chat-product-list">{message.products.map((product) => (
                  <Link className="chat-product" to={`/products/${encodeURIComponent(product.product_id)}`} key={product.product_id} onClick={() => setIsOpen(false)}>
                    <img src={getImageUrl(product.image_url)} alt="" />
                    <span className="chat-product-copy"><strong>{product.name}</strong><small>{formatPrice(product.price)} · {product.garment_type}</small><small>{product.short_description}</small><small>{product.sizes?.length ? `Stock by size: ${product.sizes.map((option) => `${option.size} ${option.quantity}`).join(' · ')}` : 'Size stock unavailable'}</small></span>
                    <span className="chat-product-arrow" aria-hidden="true">↗</span>
                  </Link>
                ))}</div> : null}
              </div>
            ))}
            {messages.length === 1 && !pending && !historyLoading && !authLoading && (
              <div className="chat-suggestions" aria-label="Suggested questions">
                {suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => void sendMessage(suggestion)}>{suggestion}</button>)}
              </div>
            )}
            {(pending || historyLoading || authLoading) && <div className="chat-message chat-message-waiting" role="status">{historyLoading || authLoading ? 'Loading your chat…' : 'Checking the collection…'}</div>}
            {error && <div className="chat-error" role="alert">{error}</div>}
            <div ref={latestMessageRef} />
          </div>
          <form className="chat-input-row" onSubmit={handleSend}>
            <input aria-label="Message" placeholder="Ask about the collection" value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={1200} disabled={pending || historyLoading || authLoading} />
            <button type="submit" aria-label="Send message" disabled={pending || historyLoading || authLoading || !draft.trim()}>↑</button>
          </form>
          <p className="chat-note">{account ? 'Your chat history is saved to your account.' : 'Guest chat history is not saved.'} Prices and availability use current shop listings.</p>
        </section>
      )}
      <button className="chat-launcher" onClick={() => setIsOpen((open) => !open)} aria-expanded={isOpen}>
        <span className="chat-launcher-icon" aria-hidden="true">✦</span>
        {isOpen ? 'Close chat' : 'Need a hand?'}
      </button>
    </div>
  )
}

function Layout({ children, account, authLoading, onLogout }: { children: ReactNode; account: AuthUser | null; authLoading: boolean; onLogout: () => void }) {
  return (
    <>
      <ScrollToTop />
      <Header account={account} onLogout={onLogout} />
      <main>{children}</main>
      <Footer />
      <ChatPanel account={account} authLoading={authLoading} />
    </>
  )
}

function ErrorNotice({ message }: { message: string }) {
  return <div className="notice notice-error" role="alert">{message} Start the FastAPI service to load the catalogue.</div>
}

function LoadingCards() {
  return (
    <div className="product-grid" aria-label="Loading products">
      {Array.from({ length: 4 }, (_, index) => <div className="product-skeleton" key={index} />)}
    </div>
  )
}

function ProductCard({ product }: { product: Product }) {
  return (
    <Link to={`/products/${encodeURIComponent(product.product_id)}`} className="product-card">
      <div className="product-card-image">
        <img src={getImageUrl(product.image_url)} alt={product.name} loading="lazy" />
        <span className="product-image-label">CAMPUS CUSTOMS / YALE</span>
        <span className="product-card-arrow" aria-hidden="true">↗</span>
      </div>
      <div className="product-card-meta"><span>{product.garment_type}</span><span>{formatPrice(product.price)}</span></div>
      <h3>{product.name}</h3>
      <p>{product.description}</p>
      <div className="product-card-bottom"><span className="product-card-colors">{product.colors.slice(0, 2).join(' · ') || 'Bulldog Blue collection'}</span><span className="product-card-link">View piece <b aria-hidden="true">↗</b></span></div>
    </Link>
  )
}

function ProductGrid({ products }: { products: Product[] }) {
  if (!products.length) return <div className="empty-state">No pieces matched that search. Try another name or garment type.</div>
  return <div className="product-grid">{products.map((product) => <ProductCard product={product} key={product.product_id} />)}</div>
}

function SectionHeading({ eyebrow, title, body, link }: { eyebrow: string; title: string; body?: string; link?: ReactNode }) {
  return (
    <div className="section-heading">
      <div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2>{body && <p>{body}</p>}</div>
      {link}
    </div>
  )
}

function HomePage({ products, loading, error }: { products: Product[]; loading: boolean; error: string }) {
  const feature = products[3] ?? products[0]
  const featured = products.slice(0, 4)
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow eyebrow-light">A LITTLE YALE, A LOT OF YOU</span>
          <h1>Find your<br /><em>place</em> in blue.</h1>
          <p>From your college to your favorite team, discover easy-to-wear pieces that carry a bit of campus wherever the day takes you.</p>
          <div className="hero-actions"><Link className="button button-gold" to="/products">Explore the collection <span aria-hidden="true">→</span></Link><Link className="text-link text-link-light" to="/about">Meet Campus Customs</Link></div>
          <div className="hero-index"><span>01</span><span className="hero-rule"/><span>YALE BULLDOG BLUE</span></div>
        </div>
        <div className="hero-art" aria-label="Featured Yale apparel">
          <div className="hero-image-frame">
            {feature ? <img src={getImageUrl(feature.image_url)} alt={feature.name} /> : <div className="hero-image-placeholder"><span>YALE</span></div>}
            <div className="image-caption"><span>COLLEGE DAYS, EVERY DAY</span><span>NEW HAVEN · EST. 1975</span></div>
          </div>
          <div className="hero-stamp"><span>MADE FOR</span><strong>THE<br />BULLDOG<br />BLUE</strong><span>SPIRIT</span></div>
          <div className="hero-scribble" aria-hidden="true">Y</div>
        </div>
        <div className="hero-bottom"><span>COLLEGE · COMMUNITY · CAMPUS LIFE</span><span>SCROLL TO EXPLORE ↓</span></div>
      </section>

      <section className="intro-strip page-shell">
        <p className="intro-large">More than a sweatshirt.<br /><em>A piece of your campus story.</em></p>
        <p className="intro-note">Browse a collection shaped around the people and places that make Yale feel like yours—from residential college classics to the next big game.</p>
      </section>

      <section className="home-products page-shell">
        <SectionHeading eyebrow="THE CAMPUS EDIT" title="Everyday favorites,\nYale at heart." body="A few good places to start exploring." link={<Link className="text-link" to="/products">Shop all products <span aria-hidden="true">↗</span></Link>} />
        {loading && <LoadingCards />}
        {error && <ErrorNotice message={error} />}
        {!loading && !error && <ProductGrid products={featured} />}
      </section>

      <section className="category-band">
        <div className="category-inner page-shell">
          <div className="category-copy"><span className="eyebrow eyebrow-light">YOUR CAMPUS, YOUR WAY</span><h2>Find the thread<br />that feels like <em>you.</em></h2><p>Choose the corner of campus you call yours, or browse until something clicks.</p><Link className="button button-outline-light" to="/products">Browse all pieces <span aria-hidden="true">→</span></Link></div>
          <div className="category-list">
            <Link to="/products?search=college">01 <span>Residential colleges</span><b>↗</b></Link>
            <Link to="/products?search=sport">02 <span>Teams & sport</span><b>↗</b></Link>
            <Link to="/products?search=school">03 <span>Schools & studies</span><b>↗</b></Link>
            <Link to="/products?search=yale">04 <span>Yale, together</span><b>↗</b></Link>
          </div>
        </div>
      </section>

      <section className="home-about page-shell">
        <div className="home-about-mark"><span className="decorative-y">Y</span><span className="eyebrow">NEW HAVEN ROOTS</span></div>
        <div><h2>Good gear.<br /><em>Good stories.</em></h2><p>Campus Customs has been part of the Yale neighborhood since 1975. Today, its Yale Bulldog Blue collection brings campus-inspired apparel together in one place.</p><Link className="text-link" to="/about">A little more about us <span aria-hidden="true">↗</span></Link></div>
      </section>
    </>
  )
}

function ProductsPage({ products, loading, error }: { products: Product[]; loading: boolean; error: string }) {
  const params = new URLSearchParams(window.location.search)
  const [query, setQuery] = useState(params.get('search') ?? '')
  const [category, setCategory] = useState('All pieces')
  const [sortOrder, setSortOrder] = useState<ProductSortOrder>('featured')
  const categories = ['All pieces', ...Array.from(new Set(products.map((product) => product.garment_type))).sort()]
  const matchingProducts = products.filter((product) => {
    const matchesCategory = category === 'All pieces' || product.garment_type === category
    const terms = `${product.name} ${product.description} ${product.garment_type} ${product.search_tags.join(' ')}`.toLowerCase()
    return matchesCategory && terms.includes(query.trim().toLowerCase())
  })
  const filtered = sortProducts(matchingProducts, sortOrder)
  return (
    <section className="page-shell collection-page">
      <div className="page-kicker"><span>YALE BULLDOG BLUE</span><span>01 / THE COLLECTION</span></div>
      <div className="collection-title-row"><div><span className="eyebrow">FIND YOUR CAMPUS FAVORITE</span><h1>Made for <em>your</em><br />kind of Yale.</h1></div><p>From familiar college names to game-day layers, start with what you love and see where it takes you.</p></div>
      <div className="collection-toolbar">
        <label className="search-field"><span aria-hidden="true">⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search the collection" aria-label="Search products" /></label>
        <label className="filter-field"><span>GARMENT</span><select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Filter by garment type">{categories.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label className="filter-field"><span>SORT</span><select value={sortOrder} onChange={(event) => setSortOrder(event.target.value as ProductSortOrder)} aria-label="Sort products"><option value="featured">Featured</option><option value="price-low">Price: low to high</option><option value="price-high">Price: high to low</option><option value="name">Name: A to Z</option></select></label>
        {!loading && <span className="result-count">{filtered.length} {filtered.length === 1 ? 'piece' : 'pieces'}</span>}
      </div>
      {loading && <LoadingCards />}
      {error && <ErrorNotice message={error} />}
      {!loading && !error && <ProductGrid products={filtered} />}
    </section>
  )
}

function ProductPage() {
  const { productId = '' } = useParams()
  const [product, setProduct] = useState<Product | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let current = true
    setLoading(true)
    setError('')
    getProduct(productId)
      .then((item) => { if (current) setProduct(item) })
      .catch((reason: unknown) => { if (current) setError(reason instanceof Error ? reason.message : 'This product could not be loaded.') })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [productId])
  if (loading) return <section className="page-shell detail-loading"><div className="product-skeleton"/><div className="skeleton-copy"/></section>
  if (error) return <section className="page-shell detail-message"><ErrorNotice message={error} /><Link className="text-link" to="/products">Back to products ↗</Link></section>
  if (!product) return <section className="page-shell detail-message"><h1>We couldn't find that piece.</h1><Link className="text-link" to="/products">Return to the collection ↗</Link></section>
  return (
    <section className="page-shell product-detail">
      <div className="breadcrumb"><Link to="/products">Products</Link><span>/</span><span>{product.name}</span></div>
      <div className="detail-layout">
        <div className="detail-image"><img src={getImageUrl(product.image_url)} alt={product.name} /><span className="detail-image-note">YALE BULLDOG BLUE · CAMPUS CUSTOMS</span></div>
        <div className="detail-copy"><span className="eyebrow">{product.garment_type}</span><h1>{product.name}</h1><div className="detail-price">{formatPrice(product.price)}</div><div className="detail-divider"/><p className="detail-description">{product.description}</p>
          {product.colors.length > 0 && <div className="detail-colors"><span className="field-label">COLOR NOTES</span><p>{product.colors.join(' · ')}</p></div>}
          <div className="stock-section"><span className="field-label">SIZES & AVAILABILITY</span>{product.sizes?.length ? <ul className="stock-list">{product.sizes.map((option) => <li key={option.size}><span>{option.size}</span><span className={option.quantity > 0 ? 'in-stock' : 'out-stock'}>{option.quantity > 0 ? `${option.quantity} in stock` : 'Out of stock'}</span></li>)}</ul> : <p className="muted-copy">Size and stock details are not currently available.</p>}</div>
          <Link to="/products" className="text-link detail-back">← Back to the collection</Link>
        </div>
      </div>
      <div className="detail-footnote"><span>01</span><p>Campus favorite, ready for your next chapter.</p><span>NEW HAVEN · YALE BULLDOG BLUE</span></div>
    </section>
  )
}

function AboutPage() {
  return (
    <>
      <section className="about-hero">
        <div className="about-hero-inner page-shell"><span className="eyebrow eyebrow-light">A NEW HAVEN ORIGINAL</span><h1>Campus is made<br />of <em>small things.</em></h1><p>A familiar sweatshirt. A team you have cheered for. A college name that still feels like home.</p></div>
        <span className="about-hero-seal">CC<br /><small>1975</small></span>
      </section>
      <section className="about-story page-shell">
        <div className="about-side"><span className="eyebrow">OUR STORY</span><span className="about-side-number">01 — 03</span></div>
        <div className="about-story-copy"><h2>A local story,<br /><em>still unfolding.</em></h2><p>Campus Customs began in New Haven in 1975 as a shop for Yale keepsakes. Over time, the work grew to include custom apparel, decoration, and online stores—while staying close to the community that started it.</p><p>Yale Bulldog Blue carries that connection into a collection inspired by campus life. Browse by residential college, sport, school, or family, then find a piece that feels personal to you.</p><p>We built this shop to make that search feel simple: good campus gear, clear product details, and room to find your own favorite.</p><Link className="text-link" to="/products">Explore the collection <span aria-hidden="true">↗</span></Link></div>
      </section>
      <section className="about-values">
        <div className="page-shell about-values-inner"><span className="eyebrow eyebrow-light">A FEW THINGS WE BELIEVE</span><div className="value-grid"><article><span>01</span><h3>Place matters.</h3><p>Campus has a way of turning names, colors, and traditions into something you carry with you.</p></article><article><span>02</span><h3>Make it personal.</h3><p>Your favorite corner of Yale may be a team, a college, a classroom, or the people you share it with.</p></article><article><span>03</span><h3>Wear it often.</h3><p>We love the pieces that move easily from a campus walk to an ordinary day at home.</p></article></div></div>
      </section>
      <section className="about-close page-shell"><div><span className="eyebrow">READY TO LOOK AROUND?</span><h2>Your next campus<br /><em>favorite is here.</em></h2></div><Link className="button button-navy" to="/products">Shop the collection <span aria-hidden="true">→</span></Link></section>
    </>
  )
}

function AccountPage({ mode, onAuth }: { mode: 'login' | 'create'; onAuth: (account: AuthUser) => void }) {
  const isCreate = mode === 'create'
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setMessage('')
    setError('')
    const form = event.currentTarget
    const fields = new FormData(form)
    const email = String(fields.get('email') ?? '')
    const password = String(fields.get('password') ?? '')
    try {
      const account = isCreate
        ? await registerAccount({
          first_name: String(fields.get('first_name') ?? ''),
          last_name: String(fields.get('last_name') ?? ''),
          email,
          password,
          password_confirmation: String(fields.get('password_confirmation') ?? ''),
        })
        : await loginAccount({ email, password })
      onAuth(account)
      setMessage(isCreate ? 'Your account is ready. You are signed in.' : `Welcome back, ${account.first_name}.`)
      form.reset()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'We could not complete that request. Please try again.')
    } finally {
      setPending(false)
    }
  }
  return (
    <section className="account-page page-shell">
      <div className="account-card">
        <span className="eyebrow">YALE BULLDOG BLUE</span>
        <h1>{isCreate ? 'Make yourself at home.' : 'Welcome back.'}</h1>
        <p>{isCreate ? 'Create an account to keep your Campus Customs visits in one place.' : 'Log in to your Campus Customs account.'}</p>
        <form onSubmit={handleSubmit}>
          {isCreate && <div className="name-fields"><label>First name<input name="first_name" autoComplete="given-name" maxLength={80} required placeholder="First name" /></label><label>Last name<input name="last_name" autoComplete="family-name" maxLength={80} required placeholder="Last name" /></label></div>}
          <label>Email address<input name="email" type="email" autoComplete="email" maxLength={254} required placeholder="you@example.com" /></label>
          <label>Password<input name="password" type="password" autoComplete={isCreate ? 'new-password' : 'current-password'} required minLength={isCreate ? 8 : 1} maxLength={1024} placeholder={isCreate ? 'At least 8 characters' : 'Your password'} /></label>
          {isCreate && <label>Confirm password<input name="password_confirmation" type="password" autoComplete="new-password" required minLength={8} maxLength={1024} placeholder="Enter your password again" /></label>}
          <button className="button button-navy account-submit" type="submit" disabled={pending}>{pending ? 'Please wait…' : isCreate ? 'Create account' : 'Log in'} <span aria-hidden="true">→</span></button>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}
        {message && <p className="form-note" role="status">{message}</p>}
        <div className="account-switch">{isCreate ? <>Already have an account? <Link to="/login">Log in</Link></> : <>New to Campus Customs? <Link to="/create-account">Create an account</Link></>}</div>
      </div>
      <div className="account-side"><span className="eyebrow eyebrow-light">MADE FOR CAMPUS LIFE</span><p>Find the pieces that bring your corner of Yale along for the ride.</p><span className="account-side-y">Y</span></div>
    </section>
  )
}

function NotFound() {
  return <section className="page-shell not-found"><span className="eyebrow">404 · OFF THE MAP</span><h1>Looks like this<br />isn't your <em>corner.</em></h1><Link className="button button-navy" to="/">Back to Home <span aria-hidden="true">→</span></Link></section>
}

export default function App() {
  const [products, setProducts] = useState<Product[]>([])
  const [account, setAccount] = useState<AuthUser | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let current = true
    getCurrentUser()
      .then((user) => { if (current) setAccount(user) })
      .catch(() => { if (current) setAccount(null) })
      .finally(() => { if (current) setAuthLoading(false) })
    return () => { current = false }
  }, [])
  useEffect(() => {
    let current = true
    getProducts()
      .then((items) => { if (current) setProducts(items) })
      .catch((reason: unknown) => { if (current) setError(reason instanceof Error ? reason.message : 'The catalogue could not be loaded.') })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [])
  async function handleLogout() {
    try {
      await logoutAccount()
    } catch {
      // Clear the local account view even if a stale session cannot be reached.
    } finally {
      setAccount(null)
    }
  }
  return (
    <Layout account={account} authLoading={authLoading} onLogout={handleLogout}>
      <Routes>
        <Route path="/" element={<HomePage products={products} loading={loading} error={error} />} />
        <Route path="/products" element={<ProductsPage products={products} loading={loading} error={error} />} />
        <Route path="/products/:productId" element={<ProductPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/login" element={<AccountPage mode="login" onAuth={setAccount} />} />
        <Route path="/create-account" element={<AccountPage mode="create" onAuth={setAccount} />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  )
}
