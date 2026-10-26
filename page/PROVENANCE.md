# Provenance

Every file in the first table is copied from the frozen frontend, the private repository `kimeltech/ecosemantic_frontend`, commit `2ba1b0480f4133d775afed3e1c3e828070a2f9c9`, with the changes named; every commit in it is Carlos Gaete-Morales's. A row that names a commit of its own is copied at that commit rather than at the one above. The file in the second table is taken from shadcn/ui. Nothing is copied from openLCA.

| Source | Destination | Changed |
| ------ | ----------- | ------- |
| `public/logo.svg` at commit `612ce2d31b4dceb1d9bf0bc857da3d8f629f0102` | `src/assets/logo.svg` | none |
| `src/components/workspace/edges/FlowEdge.tsx:32-43` (`formatAmount`) | `src/lib/format.ts` | moved out of the component into an exported function; its parameter renamed from `amount` to `value`; `Math.abs` read once into `magnitude`; a zero renders as `0`; `formatShare` and `shortHash` added |
| `src/components/workspace/edges/FlowEdge.tsx` | `src/editors/graph/FlowEdge.tsx` | removed the `// Format amount with appropriate precision` comment; `formatAmount` imported from `@/lib/format` instead of redeclared inline; `FlowEdgeData` exported, extended with `formula` and with `Record<string, unknown>`, and `FlowEdgeType` added, so the edge is typed as `EdgeProps<FlowEdgeType>` instead of `data as unknown as FlowEdgeData`; the edge's inline `style` dropped whole: its `stroke: '#8b5cf6'`, so the stroke is xyflow's `--xy-edge-stroke`, which `src/styles/index.css` sets per theme to the `link-stroke` token; its `strokeWidth: 3`, so `src/styles/index.css`'s `.react-flow__edge-flow` and `.hot` rules set the width; and its `flowAnimation` dash animation, since no such keyframe is defined in this app; the label's classes changed from `px-2 py-1 rounded-md bg-violet-500/90 text-white text-xs font-medium shadow-lg border border-violet-400/50` to `nodrag nopan rounded-md bg-selected px-1.5 py-0.5 text-[11px] font-medium shadow`: the padding reduced from `px-2 py-1` to `px-1.5 py-0.5`, the violet background replaced with the `bg-selected` theme class, the `text-white` text colour dropped so the label takes the theme's foreground, `text-xs` replaced with `text-[11px]`, the `shadow-lg` shadow reduced to `shadow`, the `border border-violet-400/50` border dropped, and `nodrag nopan` added; the label shows `ƒ` with the formula as its `title` when `data.formula` is set |
| `src/index.css:110-135`, `:150`, `:179-197`, `:200-204`, `:223-225`, `:228-230`, `:253-255`, `:257-258` (the theme scheme and its `@theme` block) | `src/styles/index.css` | the `.dark` token values for `--background` through `--ring` (`:110-135`) and `--success-foreground` (`:150`) copied under the selector `:root, [data-theme="ecosemantic"]` in place of `.dark`, with every comment removed; the light `:root` block (`:23-106`) not copied, `--radius` taken from it and set to `0.5rem` in place of `0.625rem`; `--success`, `--success-muted`, `--warning`, `--warning-foreground` and `--warning-muted` set to the logo's green and orange in place of Tailwind's green and amber; the five `--chart-*` tokens replaced by the seven logo gradient stops; `--highlight`, `--chrome`, `--selected`, `--node-border`, `--link-stroke`, `--xy-edge-stroke`, the eleven `--role-*` tokens and `color-scheme` added; the `[data-theme="openlca"]` block written for this app, not copied; the `--brand-*`, `--info*`, `--promo*`, `--discord` and `--surface-*` tokens and their mappings dropped; the `@theme` mappings for `background` through `ring` (`:179-197`), `chart-1` to `chart-5` (`:200-204`), `success` (`:223-225`) and `warning` (`:228-230`) copied with their comments removed, and mappings for `chart-6`, `chart-7`, `highlight`, `chrome`, `selected`, `node-border`, `link-stroke`, the `role-*` tokens and `radius-sm`, `radius-md` and `radius-lg` added; the base layer's `* { @apply border-border; }` (`:253-255`) copied and its `body` rule (`:257-258`) kept to `bg-background text-foreground` with `font-sans` and `font-feature-settings` dropped and `text-[13px] leading-snug antialiased` added; the regression-guard comment (`:1-16`), the `report.css` import (`:18`), the streamdown `@source` (`:21`), the `transition-colors` base rule (`:263-265`) and everything from the gradient utilities (`:269`) to the end of the file dropped; the `flash` keyframes, the `.react-flow__edge` rules and the `text-role-*` `@source inline` safelist added |
| `src/lib/utils.ts` | `src/lib/utils.ts` | kept only `cn`; dropped `formatNumber`, `formatDate`, `formatRelativeDate`, `copyToClipboard`, `downloadFile`, `downloadJSON`, `isValidEmail`, `generateId`, `debounce`, `throttle`, `getEnvConfig`, `isAuthenticated`, `getAuthToken`, `removeAuthToken`, `formatLCAResult`, `parseMethodSpecification`, `formatTierName`, `calculateUsagePercentage`, `getUsageStatusColor`, `sleep`, `retryWithBackoff` and their comments |
| `src/components/ui/alert-dialog.tsx` | `src/components/ui/alert-dialog.tsx` | none |
| `src/components/ui/alert.tsx` | `src/components/ui/alert.tsx` | removed a `// Semantic status variants` comment; removed the `info` and `promo` variants, whose classes referenced colour tokens neither theme defines |
| `src/components/ui/badge.tsx` | `src/components/ui/badge.tsx` | removed a `// Semantic status variants` comment; removed the `info` and `promo` variants, whose classes referenced colour tokens neither theme defines |
| `src/components/ui/button.tsx` | `src/components/ui/button.tsx` | none |
| `src/components/ui/button-variants.ts` | `src/components/ui/button-variants.ts` | removed a three-line rationale comment above `buttonVariants` and a `// Semantic status variants` comment; removed the `info` and `promo` variants, whose classes referenced colour tokens neither theme defines |
| `src/components/ui/card.tsx` | `src/components/ui/card.tsx` | none |
| `src/components/ui/collapsible.tsx` | `src/components/ui/collapsible.tsx` | none |
| `src/components/ui/dialog.tsx` | `src/components/ui/dialog.tsx` | none |
| `src/components/ui/dropdown-menu.tsx` | `src/components/ui/dropdown-menu.tsx` | none |
| `src/components/ui/input.tsx` | `src/components/ui/input.tsx` | none |
| `src/components/ui/label.tsx` | `src/components/ui/label.tsx` | none |
| `src/components/ui/scroll-area.tsx` | `src/components/ui/scroll-area.tsx` | none |
| `src/components/ui/select.tsx` | `src/components/ui/select.tsx` | removed two leftover debug `console.log` calls in the `SelectTrigger` and `SelectItem` click handlers |
| `src/components/ui/separator.tsx` | `src/components/ui/separator.tsx` | none |
| `src/components/ui/sheet.tsx` | `src/components/ui/sheet.tsx` | none |
| `src/components/ui/switch.tsx` | `src/components/ui/switch.tsx` | none |
| `src/components/ui/table.tsx` | `src/components/ui/table.tsx` | none |
| `src/components/ui/tabs.tsx` | `src/components/ui/tabs.tsx` | none |
| `src/components/ui/textarea.tsx` | `src/components/ui/textarea.tsx` | none |
| `src/components/ui/tooltip.tsx` | `src/components/ui/tooltip.tsx` | `Tooltip` renders the Radix root alone instead of wrapping each tooltip in a provider of its own, so the one provider in `src/App.tsx` holds the delays; `TooltipProvider` defaults `delayDuration` to `400` in place of `0` and passes `skipDelayDuration`, default `150` |

| Source | Destination | Changed |
| ------ | ----------- | ------- |
| shadcn/ui, `apps/v4/registry/new-york-v4/ui/menubar.tsx` at commit `c257f688cf4de7ec10cc1be84cad29cd4631182c` | `src/components/ui/menubar.tsx` | written again after its component names and `data-slot` attributes: eight of its sixteen components kept (`Menubar`, `MenubarMenu`, `MenubarTrigger`, `MenubarContent`, `MenubarItem`, `MenubarSub`, `MenubarSubTrigger`, `MenubarSubContent`), their shared class strings held in `CONTENT` and `ITEM`, and the checkbox, radio, label, separator, group, portal and shortcut parts left out |

## shadcn/ui

The components under `src/components/ui/` follow shadcn/ui (`github.com/shadcn-ui/ui`), the `new-york` style the frozen frontend's `components.json` names, and the frozen frontend took them from there. shadcn/ui is distributed under the MIT licence, whose notice they carry with them:

```
MIT License

Copyright (c) 2023 shadcn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
