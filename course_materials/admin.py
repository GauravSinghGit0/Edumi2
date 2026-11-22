from django.contrib import admin
from .models import MaterialUnit, StudyMaterial, MaterialChunk, MaterialBookmark

@admin.register(MaterialUnit)
class MaterialUnitAdmin(admin.ModelAdmin):
    list_display = ('title', 'classroom', 'order', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('title', 'classroom__title')

@admin.register(StudyMaterial)
class StudyMaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'material_type', 'classroom', 'is_published', 'rag_indexed')
    list_filter = ('material_type', 'is_published', 'rag_indexed', 'created_at')
    search_fields = ('title', 'description', 'classroom__title')
    readonly_fields = ('created_at', 'updated_at', 'rag_indexed_at')

@admin.register(MaterialChunk)
class MaterialChunkAdmin(admin.ModelAdmin):
    list_display = ('material', 'chunk_index', 'token_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('material__title', 'chunk_text')

@admin.register(MaterialBookmark)
class MaterialBookmarkAdmin(admin.ModelAdmin):
    list_display = ('material', 'user', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('material__title', 'user__username')
