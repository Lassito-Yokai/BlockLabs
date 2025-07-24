from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.contrib import messages
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from client.library.models import Document, DocumentCategory, RegulatoryAuthority, DocumentTranslation
# Import des modèles RawDocument pour la bibliothèque
from rawdocs.models import RawDocument
import json
import logging
import os

logger = logging.getLogger(__name__)

def library_dashboard(request):
    """Vue principale de la library - affiche les documents des métadonneurs"""
    # Statistiques générales basées sur RawDocument
    total_documents = RawDocument.objects.filter(is_validated=True).count()
    pending_validation = RawDocument.objects.filter(is_validated=False).count()
    total_metadonneurs = RawDocument.objects.values('owner').distinct().count()
    
    # Documents récents validés avec métadonnées
    recent_documents = RawDocument.objects.filter(
        is_validated=True
    ).select_related('owner').order_by('-created_at')[:10]
    
    # Statistiques par type de document
    document_type_stats = RawDocument.objects.filter(
        is_validated=True
    ).exclude(doc_type='').values('doc_type').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    # Statistiques par pays
    country_stats = RawDocument.objects.filter(
        is_validated=True
    ).exclude(country='').values('country').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    context = {
        'total_documents': total_documents,
        'pending_validation': pending_validation, 
        'total_metadonneurs': total_metadonneurs,
        'recent_documents': recent_documents,
        'document_type_stats': document_type_stats,
        'country_stats': country_stats,
    }
    
    return render(request, 'client/library/dashboard.html', context)

def document_list(request):
    """Liste des documents RawDocument avec filtrage"""
    # Paramètres de filtrage
    search = request.GET.get('search', '')
    document_type = request.GET.get('type', '')
    country = request.GET.get('country', '')
    language = request.GET.get('language', '')
    validation_status = request.GET.get('status', 'validated')
    
    # Construction de la requête sur RawDocument
    documents_qs = RawDocument.objects.select_related('owner').all()
    
    # Filtrer seulement les documents validés par défaut
    if validation_status == 'validated':
        documents_qs = documents_qs.filter(is_validated=True)
    elif validation_status == 'pending':
        documents_qs = documents_qs.filter(is_validated=False)
    
    if search:
        documents_qs = documents_qs.filter(
            Q(title__icontains=search) | 
            Q(source__icontains=search) |
            Q(context__icontains=search)
        )
    
    if document_type:
        documents_qs = documents_qs.filter(doc_type__icontains=document_type)
    
    if country:
        documents_qs = documents_qs.filter(country__icontains=country)
    
    if language:
        documents_qs = documents_qs.filter(language__icontains=language)
    
    documents_qs = documents_qs.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(documents_qs, 20)
    page_number = request.GET.get('page')
    documents = paginator.get_page(page_number)
    
    # Options de filtrage basées sur RawDocument
    document_types = RawDocument.objects.filter(is_validated=True).exclude(doc_type='').values_list('doc_type', flat=True).distinct()
    countries = RawDocument.objects.filter(is_validated=True).exclude(country='').values_list('country', flat=True).distinct()
    languages = RawDocument.objects.filter(is_validated=True).exclude(language='').values_list('language', flat=True).distinct()
    
    context = {
        'documents': documents,
        'document_types': document_types,
        'countries': countries,
        'languages': languages,
        'filters': {
            'search': search,
            'type': document_type,
            'country': country,
            'language': language,
            'status': validation_status,
        }
    }
    
    return render(request, 'client/library/document_list.html', context)

def document_detail(request, pk):
    """Détail d'un RawDocument avec ses métadonnées"""
    document = get_object_or_404(RawDocument, pk=pk, is_validated=True)
    
    # Obtenir les métadonnées extraites
    from rawdocs.utils import extract_metadonnees
    try:
        metadata = extract_metadonnees(document.file.path, document.url or "")
    except:
        metadata = {}
    
    # Documents similaires (même type et pays)
    related_documents = RawDocument.objects.filter(
        doc_type=document.doc_type,
        country=document.country,
        is_validated=True
    ).exclude(pk=document.pk)[:5]
    
    context = {
        'document': document,
        'metadata': metadata,
        'related_documents': related_documents,
    }
    
    return render(request, 'client/library/document_detail.html', context)

def download_document(request, pk):
    """Télécharger un RawDocument"""
    document = get_object_or_404(RawDocument, pk=pk, is_validated=True)
    
    if not document.file:
        raise Http404("Fichier non trouvé")
    
    # Retourner le fichier
    response = HttpResponse(document.file.read(), content_type='application/pdf')
    filename = document.file.name.split('/')[-1]
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@api_view(['GET'])
def search_documents(request):
    """API de recherche de documents"""
    query = request.GET.get('q', '')
    limit = int(request.GET.get('limit', 10))
    
    if not query:
        return Response([])
    
    documents = Document.objects.filter(
        Q(title__icontains=query) | 
        Q(description__icontains=query) |
        Q(tags__icontains=query),
        validation_status='validated'
    ).select_related('authority', 'category')[:limit]
    
    results = []
    for doc in documents:
        results.append({
            'id': doc.id,
            'title': doc.title,
            'authority': doc.authority.name,
            'type': doc.get_document_type_display(),
            'publication_date': doc.publication_date.isoformat() if doc.publication_date else None,
            'url': doc.get_absolute_url()
        })
    
    return Response(results)

@api_view(['GET'])
def document_metadata(request, pk):
    """API pour récupérer les métadonnées d'un document"""
    document = get_object_or_404(Document, pk=pk)
    
    metadata = {
        'id': document.id,
        'title': document.title,
        'description': document.description,
        'document_type': document.get_document_type_display(),
        'authority': {
            'name': document.authority.name,
            'code': document.authority.code,
            'country': document.authority.country,
        },
        'category': document.category.name if document.category else None,
        'language': document.get_language_display(),
        'publication_date': document.publication_date.isoformat() if document.publication_date else None,
        'effective_date': document.effective_date.isoformat() if document.effective_date else None,
        'expiry_date': document.expiry_date.isoformat() if document.expiry_date else None,
        'reference_number': document.reference_number,
        'source_url': document.source_url,
        'tags': document.tags_list,
        'ctd_section': document.ctd_section,
        'therapeutic_area': document.therapeutic_area,
        'file_size': document.formatted_file_size,
        'file_extension': document.file_extension,
        'validation_status': document.get_validation_status_display(),
        'validated_by': document.validated_by,
        'validation_date': document.validation_date.isoformat() if document.validation_date else None,
        'view_count': document.view_count,
        'download_count': document.download_count,
        'created_at': document.created_at.isoformat(),
        'updated_at': document.updated_at.isoformat(),
    }
    
    return Response(metadata)

def upload_document(request):
    """Interface d'upload de document avec traitement du formulaire"""
    if request.method == 'POST':
        try:
            # Récupération des données du formulaire
            file = request.FILES.get('file')
            title = request.POST.get('title', '').strip()
            description = request.POST.get('description', '').strip()
            document_type = request.POST.get('document_type')
            language = request.POST.get('language')
            authority_id = request.POST.get('authority')
            category_id = request.POST.get('category')
            reference_number = request.POST.get('reference_number', '').strip()
            source_url = request.POST.get('source_url', '').strip()
            publication_date = request.POST.get('publication_date')
            effective_date = request.POST.get('effective_date')
            expiry_date = request.POST.get('expiry_date')
            ctd_section = request.POST.get('ctd_section', '').strip()
            therapeutic_area = request.POST.get('therapeutic_area', '').strip()
            tags = request.POST.get('tags', '').strip()
            validated_by = request.POST.get('validated_by', 'RegX Admin').strip()
            validation_notes = request.POST.get('validation_notes', '').strip()

            # Validation des champs obligatoires
            if not all([file, title, document_type, language, authority_id, publication_date]):
                messages.error(request, "Veuillez remplir tous les champs obligatoires.")
                return redirect('library:upload_document')

            # Récupération des objets liés
            try:
                authority = RegulatoryAuthority.objects.get(id=authority_id)
            except RegulatoryAuthority.DoesNotExist:
                messages.error(request, "Autorité réglementaire invalide.")
                return redirect('library:upload_document')

            category = None
            if category_id:
                try:
                    category = DocumentCategory.objects.get(id=category_id)
                except DocumentCategory.DoesNotExist:
                    pass

            # Calcul de la taille du fichier
            file_size = file.size if file else 0

            # Création du document
            document = Document.objects.create(
                title=title,
                description=description,
                document_type=document_type,
                category=category,
                authority=authority,
                source_url=source_url,
                reference_number=reference_number,
                file=file,
                file_size=file_size,
                language=language,
                publication_date=publication_date,
                effective_date=effective_date if effective_date else None,
                expiry_date=expiry_date if expiry_date else None,
                validation_status='validated',  # Auto-validation pour le MVP
                validated_by=validated_by,
                validation_date=timezone.now(),
                validation_notes=validation_notes,
                tags=tags,
                ctd_section=ctd_section,
                therapeutic_area=therapeutic_area,
                created_by=validated_by,
            )

            logger.info(f"Document '{title}' uploaded successfully with ID {document.id}")
            messages.success(request, f"Document '{title}' a été uploadé avec succès!")
            
            return redirect('library:document_detail', pk=document.id)

        except Exception as e:
            logger.error(f"Error uploading document: {e}")
            messages.error(request, f"Erreur lors de l'upload du document: {str(e)}")
            return redirect('library:upload_document')
    
    # GET request - afficher le formulaire
    authorities = RegulatoryAuthority.objects.all().order_by('name')
    categories = DocumentCategory.objects.all().order_by('name')
    
    context = {
        'authorities': authorities,
        'categories': categories,
        'document_types': Document.DOCUMENT_TYPES,
        'languages': Document.LANGUAGES,
    }
    
    return render(request, 'client/library/upload_document.html', context)
