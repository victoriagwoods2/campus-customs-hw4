import type { Product } from './api'

export type ProductSortOrder = 'featured' | 'price-low' | 'price-high' | 'name'

export function sortProducts(products: Product[], order: ProductSortOrder): Product[] {
  if (order === 'featured') return [...products]
  return [...products].sort((first, second) => {
    if (order === 'price-low') return first.price - second.price || first.name.localeCompare(second.name)
    if (order === 'price-high') return second.price - first.price || first.name.localeCompare(second.name)
    return first.name.localeCompare(second.name)
  })
}
