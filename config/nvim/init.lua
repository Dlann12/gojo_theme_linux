-- Hollow Purple Neovim Configuration (Zero-Dependency, Instant Startup)

vim.g.mapleader = " "

local opt = vim.opt
opt.number = true
opt.relativenumber = true
opt.cursorline = true
opt.termguicolors = true
opt.signcolumn = "yes"
opt.scrolloff = 6
opt.sidescrolloff = 6
opt.wrap = false
opt.expandtab = true
opt.shiftwidth = 2
opt.tabstop = 2
opt.smartindent = true
opt.ignorecase = true
opt.smartcase = true
opt.incsearch = true
opt.hlsearch = true
opt.mouse = "a"
opt.splitright = true
opt.splitbelow = true
opt.updatetime = 250
opt.laststatus = 2
opt.showmode = false

-- Persistent undo history
local undo_dir = vim.fn.stdpath("state") .. "/undo"
vim.fn.mkdir(undo_dir, "p")
opt.undofile = true
opt.undodir = undo_dir

-- Hollow Purple Colorscheme (transparent background to blend with cosmic-term)
vim.cmd("highlight clear")
if vim.fn.exists("syntax_on") == 1 then
  vim.cmd("syntax reset")
end
vim.g.colors_name = "hollow_purple"

local hl = vim.api.nvim_set_hl
local c = {
  bg      = "NONE",
  bg_alt  = "#18192b",
  bg_sel  = "#2e1f4d",
  fg      = "#eef2ff",
  muted   = "#64748b",
  comment = "#7e8ba3",
  purple  = "#c084fc",
  violet  = "#a855f7",
  cyan    = "#38bdf8",
  green   = "#34d399",
  amber   = "#fbbf24",
  pink    = "#f472b6",
  red     = "#f87171",
  border  = "#6d4aa6",
}

hl(0, "Normal",         { fg = c.fg, bg = c.bg })
hl(0, "NormalFloat",    { fg = c.fg, bg = c.bg_alt })
hl(0, "FloatBorder",    { fg = c.purple, bg = c.bg_alt })
hl(0, "EndOfBuffer",    { fg = "#2a2d45", bg = c.bg })
hl(0, "SignColumn",     { bg = c.bg })
hl(0, "LineNr",         { fg = c.muted, bg = c.bg })
hl(0, "CursorLineNr",   { fg = c.purple, bold = true, bg = c.bg_alt })
hl(0, "CursorLine",     { bg = c.bg_alt })
hl(0, "Visual",         { bg = c.bg_sel })
hl(0, "Search",         { fg = "#0d0e1a", bg = c.cyan, bold = true })
hl(0, "IncSearch",      { fg = "#0d0e1a", bg = c.purple, bold = true })
hl(0, "MatchParen",     { fg = c.amber, bg = c.bg_sel, bold = true })
hl(0, "VertSplit",      { fg = c.border })
hl(0, "Pmenu",          { fg = c.fg, bg = c.bg_alt })
hl(0, "PmenuSel",       { fg = "#0d0e1a", bg = c.purple, bold = true })
hl(0, "StatusLine",     { fg = c.fg, bg = "#1c1836" })
hl(0, "StatusLineNC",   { fg = c.muted, bg = "#121320" })
hl(0, "StatusMode",     { fg = "#0d0e1a", bg = c.purple, bold = true })
hl(0, "StatusFile",     { fg = c.cyan, bg = "#1c1836", bold = true })
hl(0, "StatusMeta",     { fg = c.purple, bg = "#1c1836" })

-- Syntax Groups
hl(0, "Comment",        { fg = c.comment, italic = true })
hl(0, "Constant",       { fg = c.amber })
hl(0, "String",         { fg = c.green })
hl(0, "Number",         { fg = c.amber })
hl(0, "Boolean",        { fg = c.pink, bold = true })
hl(0, "Identifier",     { fg = c.fg })
hl(0, "Function",       { fg = c.cyan, bold = true })
hl(0, "Statement",      { fg = c.purple, bold = true })
hl(0, "Keyword",        { fg = c.purple, italic = true })
hl(0, "Operator",       { fg = c.pink })
hl(0, "PreProc",        { fg = c.pink })
hl(0, "Type",           { fg = c.cyan })
hl(0, "Special",        { fg = c.amber })
hl(0, "Error",          { fg = c.red, bold = true })
hl(0, "Todo",           { fg = "#0d0e1a", bg = c.amber, bold = true })
hl(0, "DiffAdd",        { fg = c.green, bg = "#102a22" })
hl(0, "DiffDelete",     { fg = c.red, bg = "#2c141c" })
hl(0, "DiffChange",     { fg = c.cyan, bg = "#122438" })

-- Clean Custom Statusline
function _G.HollowStatusLine()
  local modes = {
    n = "NORMAL", i = "INSERT", v = "VISUAL", V = "V-LINE",
    ["\22"] = "V-BLOCK", c = "COMMAND", R = "REPLACE", t = "TERM",
  }
  local m = modes[vim.fn.mode()] or "NORMAL"
  return table.concat({
    "%#StatusMode# ", m, " %#StatusLine#",
    "%#StatusFile#  %f %m%r ",
    "%=",
    "%#StatusMeta# %{&filetype!=''?&filetype:'text'}  ·  %l:%c  ·  %p%% ",
  })
end
opt.statusline = "%!v:lua.HollowStatusLine()"

-- Quality-of-life Keymaps
local map = vim.keymap.set
map("n", "<Esc>", "<cmd>nohlsearch<CR>", { silent = true, desc = "Clear search highlight" })
map("n", "<leader>w", "<cmd>w<CR>", { desc = "Save file" })
map("n", "<leader>q", "<cmd>q<CR>", { desc = "Quit" })
map("n", "<leader>e", "<cmd>Ex<CR>", { desc = "File explorer" })
map("n", "<C-h>", "<C-w>h", { desc = "Focus left split" })
map("n", "<C-j>", "<C-w>j", { desc = "Focus lower split" })
map("n", "<C-k>", "<C-w>k", { desc = "Focus upper split" })
map("n", "<C-l>", "<C-w>l", { desc = "Focus right split" })
map("v", "J", ":m '>+1<CR>gv=gv", { silent = true, desc = "Move selection down" })
map("v", "K", ":m '<-2<CR>gv=gv", { silent = true, desc = "Move selection up" })
