"""Site-specific WebFlow implementations. Each module here owns the quirks
of exactly one real site (its actual form URL, which fields need special
widget handling, how it advances between steps) -- the generic pieces
(mapping, widget detection/interaction, the fill loop) stay reusable in
the parent `agents` package; nothing site-specific belongs there.
"""
