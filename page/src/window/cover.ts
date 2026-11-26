import { useLayoutEffect, type RefObject } from 'react'
import { create } from 'zustand'

interface SheetTopState {
  sheetTop: number | null
  setSheetTop: (top: number | null) => void
}

/** The top of the sheet drawn over the canvas, in client pixels, and null where no sheet covers it. */
export const useSheetTop = create<SheetTopState>((set) => ({
  sheetTop: null,
  setSheetTop: (sheetTop) => set((state) => (state.sheetTop === sheetTop ? {} : { sheetTop })),
}))

/** Publishes the top the element a sheet is drawn in takes, and none once the sheet is gone. */
export function useSheetCover(sheet: RefObject<HTMLElement | null>, shown: boolean): void {
  const setSheetTop = useSheetTop((s) => s.setSheetTop)
  useLayoutEffect(() => {
    if (!shown) {
      setSheetTop(null)
      return
    }
    const element = sheet.current
    if (element === null) return
    const measure = () => setSheetTop(element.getBoundingClientRect().top)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => {
      observer.disconnect()
      setSheetTop(null)
    }
  }, [sheet, shown, setSheetTop])
}
