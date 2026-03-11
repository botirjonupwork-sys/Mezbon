import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const useBranchStore = create(
  persist(
    (set) => ({
      branches: [],
      selectedBranchId: null,
      setBranches: (branches) => set({ branches }),
      selectBranch: (id) => set({ selectedBranchId: id }),
    }),
    { name: 'admin-branch' }
  )
)
