# expert/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import user_passes_test
import uuid
import json

from .models import ExpertLog
from rawdocs.models import RawDocument, DocumentPage, Annotation, AnnotationType


def is_expert(user):
    """Check if user is in Expert group"""
    return user.groups.filter(name="Expert").exists()


def expert_required(view_func):
    """Decorator to require expert role"""
    return user_passes_test(is_expert, login_url='rawdocs:login')(view_func)


@method_decorator(expert_required, name='dispatch')
class ExpertDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'expert/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Documents ready for expert review
        ready_documents = RawDocument.objects.filter(
            is_ready_for_expert=True
        )

        # Count pending annotations across all documents
        pending_annotations = Annotation.objects.filter(
            validation_status='pending'
        ).count()

        context.update({
            'ready_documents_count': ready_documents.count(),
            'pending_annotations': pending_annotations,
            'recent_documents': ready_documents.order_by('-expert_ready_at')[:5],
        })
        return context


@method_decorator(expert_required, name='dispatch')
class DocumentReviewView(LoginRequiredMixin, TemplateView):
    template_name = 'expert/document_review.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document_id = self.kwargs['document_id']
        document = get_object_or_404(RawDocument, id=document_id)

        # Get pages with their annotations
        pages = document.pages.prefetch_related(
            'annotations__annotation_type'
        ).order_by('page_number')

        # Pagination by page
        paginator = Paginator(pages, 1)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        current_page = page_obj.object_list[0] if page_obj.object_list else None

        all_annotation_types = AnnotationType.objects.all().order_by('display_name')

        context.update({
            'document': document,
            'page_obj': page_obj,
            'current_page': current_page,
            'all_annotation_types': all_annotation_types,  # NOUVEAU
        })
        return context


@method_decorator(expert_required, name='dispatch')
class DocumentReviewListView(LoginRequiredMixin, TemplateView):
    template_name = 'expert/document_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        documents = RawDocument.objects.filter(
            is_ready_for_expert=True
        ).annotate(
            annotation_count=Count('pages__annotations'),
        ).order_by('-expert_ready_at')

        paginator = Paginator(documents, 12)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context['page_obj'] = page_obj
        return context


@expert_required
@csrf_exempt
def validate_annotation_ajax(request, annotation_id):
    """AJAX endpoint to validate/reject annotation"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            annotation = get_object_or_404(Annotation, id=annotation_id)
            action = data.get('action')

            # Save state before modification
            old_status = annotation.validation_status

            if action == 'validate':
                annotation.validation_status = 'validated'
                annotation.validated_by = request.user
                annotation.validated_at = timezone.now()
                annotation.save()

                # LOG ACTION
                log_expert_action(
                    user=request.user,
                    action='annotation_validated',
                    annotation=annotation,
                    reason=f"Manual validation by expert. Status: {old_status} → validated"
                )

                return JsonResponse({
                    'success': True,
                    'message': 'Annotation validée',
                    'status': 'validated'
                })

            elif action == 'reject':
                annotation.validation_status = 'rejected'
                annotation.validated_by = request.user
                annotation.validated_at = timezone.now()
                annotation.save()

                # LOG ACTION
                log_expert_action(
                    user=request.user,
                    action='annotation_rejected',
                    annotation=annotation,
                    reason=f"Manual rejection by expert. Status: {old_status} → rejected"
                )

                return JsonResponse({
                    'success': True,
                    'message': 'Annotation rejetée',
                    'status': 'rejected'
                })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


@expert_required
@csrf_exempt
def create_annotation_ajax(request):
    """AJAX endpoint for experts to create new annotations"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            page_id = data.get('page_id')
            text = data.get('text')
            entity_type_name = data.get('entity_type')

            # Get the page
            page = get_object_or_404(DocumentPage, id=page_id)

            # Get or create the AnnotationType
            annotation_type, created = AnnotationType.objects.get_or_create(
                name=entity_type_name,
                defaults={
                    'display_name': entity_type_name.replace('_', ' ').title(),
                    'color': '#3b82f6',
                    'description': f"Expert created type: {entity_type_name}"
                }
            )

            # Create the annotation (experts create pre-validated annotations)
            annotation = Annotation.objects.create(
                page=page,
                selected_text=text,
                annotation_type=annotation_type,
                start_pos=data.get('start_offset', 0),
                end_pos=data.get('end_offset', len(text)),
                validation_status='expert_created',
                validated_by=request.user,
                validated_at=timezone.now(),
                created_by=request.user,
                source='expert'
            )

            # LOG ACTION
            log_expert_action(
                user=request.user,
                action='annotation_created',
                annotation=annotation,
                reason=f"New annotation created by expert in page {page.page_number}"
            )

            return JsonResponse({
                'success': True,
                'annotation_id': annotation.id,
                'message': 'Annotation créée avec succès'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


@expert_required
@csrf_exempt
def modify_annotation_ajax(request, annotation_id):
    """Modify a rejected annotation"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            annotation = get_object_or_404(Annotation, id=annotation_id)

            new_text = data.get('text')
            new_entity_type_name = data.get('entity_type')

            # Save old values for logging
            old_text = annotation.selected_text
            old_entity_type_name = annotation.annotation_type.name
            old_status = annotation.validation_status

            # Get or create the new annotation type
            annotation_type, created = AnnotationType.objects.get_or_create(
                name=new_entity_type_name,
                defaults={
                    'display_name': new_entity_type_name.replace('_', ' ').title(),
                    'color': '#3b82f6',
                    'description': f"Expert type: {new_entity_type_name}"
                }
            )

            # Update the annotation
            annotation.selected_text = new_text
            annotation.annotation_type = annotation_type
            annotation.validation_status = 'validated'  # Auto-validate after expert modification
            annotation.validated_by = request.user
            annotation.validated_at = timezone.now()
            annotation.save()

            # LOG ACTION
            log_expert_action(
                user=request.user,
                action='annotation_modified',
                annotation=annotation,
                old_text=old_text,
                new_text=new_text,
                old_entity_type=old_entity_type_name,
                new_entity_type=new_entity_type_name,
                reason=f"Modification by expert. Status: {old_status} → validated"
            )

            return JsonResponse({
                'success': True,
                'message': 'Annotation modifiée et validée'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


@expert_required
@csrf_exempt
def delete_annotation_ajax(request, annotation_id):
    """Delete an annotation"""
    if request.method == 'POST':
        try:
            annotation = get_object_or_404(Annotation, id=annotation_id)

            # LOG ACTION BEFORE DELETION
            log_expert_action(
                user=request.user,
                action='annotation_deleted',
                annotation=annotation,
                reason=f"Manual deletion by expert. Annotation was: {annotation.validation_status}"
            )

            annotation.delete()

            return JsonResponse({
                'success': True,
                'message': 'Annotation supprimée'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


@expert_required
@csrf_exempt
def undo_validation_ajax(request, annotation_id):
    """Undo validation of an annotation"""
    if request.method == 'POST':
        try:
            annotation = get_object_or_404(Annotation, id=annotation_id)

            # Save state before
            old_status = annotation.validation_status
            old_validator = getattr(annotation.validated_by, 'username',
                                    'Unknown') if annotation.validated_by else 'None'

            # Reset validation status
            annotation.validation_status = 'pending'
            annotation.validated_by = None
            annotation.validated_at = None
            annotation.save()

            # LOG ACTION
            log_expert_action(
                user=request.user,
                action='validation_undone',
                annotation=annotation,
                reason=f"Validation cancelled. Status: {old_status} → pending. Originally validated by: {old_validator}"
            )

            return JsonResponse({
                'success': True,
                'message': 'Validation annulée'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


def log_expert_action(user, action, annotation, document_id=None, document_title=None,
                      old_text=None, new_text=None, old_entity_type=None, new_entity_type=None,
                      reason=None, session_id=None):
    """Helper to log expert actions"""
    if not session_id:
        session_id = str(uuid.uuid4())[:8]

    # Get annotation info
    if annotation:
        annotation_text = getattr(annotation, 'selected_text', '')
        entity_type = getattr(annotation.annotation_type, 'name', '') if hasattr(annotation, 'annotation_type') else ''
        page = getattr(annotation, 'page', None)
        original_annotator = getattr(annotation.created_by, 'username', 'Unknown') if hasattr(annotation,
                                                                                              'created_by') else 'Unknown'

        if page:
            page_id = page.id
            page_number = page.page_number
            page_text = page.cleaned_text
            document_id = page.document.id
            document_title = page.document.file.name
        else:
            page_id = page_number = None
            page_text = ''
    else:
        annotation_text = entity_type = original_annotator = ''
        page_id = page_number = None
        page_text = ''

    ExpertLog.objects.create(
        expert=user,
        session_id=session_id,
        document_id=document_id or 0,
        document_title=document_title or '',
        page_id=page_id,
        page_number=page_number,
        page_text=page_text,
        action=action,
        annotation_id=getattr(annotation, 'id', None),
        annotation_text=annotation_text,
        annotation_entity_type=entity_type,
        annotation_start_position=getattr(annotation, 'start_pos', None),
        annotation_end_position=getattr(annotation, 'end_pos', None),
        old_text=old_text or '',
        new_text=new_text or '',
        old_entity_type=old_entity_type or '',
        new_entity_type=new_entity_type or '',
        original_annotator=original_annotator,
        validation_status_before=getattr(annotation, 'validation_status', '') if annotation else '',
        validation_status_after='',
        reason=reason or '',
    )
    return session_id


@expert_required
@csrf_exempt
def create_annotation_type_ajax(request):
    """AJAX endpoint for experts to create new annotation types"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            display_name = data.get('display_name', '').strip()
            name = data.get('name', '').strip()

            if not display_name:
                return JsonResponse({'success': False, 'error': 'Display name is required'})

            # Auto-generate name if not provided
            if not name:
                name = display_name.lower().replace(' ', '_').replace('-', '_')
                # Remove any non-alphanumeric characters except underscores
                import re
                name = re.sub(r'[^\w]', '', name)

            # Check if annotation type already exists
            if AnnotationType.objects.filter(name=name).exists():
                return JsonResponse({'success': False, 'error': f'Annotation type "{name}" already exists'})

            # Create new annotation type
            annotation_type = AnnotationType.objects.create(
                name=name,
                display_name=display_name,
                color='#6f42c1',  # Purple color for expert-created types
                description=f"Expert-created annotation type: {display_name}"
            )

            # LOG ACTION
            log_expert_action(
                user=request.user,
                action='annotation_type_created',
                annotation=None,
                reason=f"Created new annotation type: {display_name} ({name})"
            )

            return JsonResponse({
                'success': True,
                'message': f'Annotation type "{display_name}" created successfully',
                'annotation_type': {
                    'id': annotation_type.id,
                    'name': annotation_type.name,
                    'display_name': annotation_type.display_name,
                    'color': annotation_type.color
                }
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


def create_product_from_annotations(document):
    """Create a product in client module from validated annotations"""
    from client.products.models import Product, ProductSpecification, ManufacturingSite

    # Get all validated annotations from this document
    validated_annotations = Annotation.objects.filter(
        page__document=document,
        validation_status__in=['validated', 'expert_created']
    )

    # Group annotations by type
    annotations_by_type = {}
    for annotation in validated_annotations:
        annotation_type = annotation.annotation_type.name.lower()
        if annotation_type not in annotations_by_type:
            annotations_by_type[annotation_type] = []
        annotations_by_type[annotation_type].append(annotation.selected_text.strip())

    # Extract product information
    product_data = {
        'name': annotations_by_type.get('product', [''])[0] or 'Unknown Product',
        'dosage': annotations_by_type.get('dosage', [''])[0] or 'N/A',
        'active_ingredient': annotations_by_type.get('substance_active', ['N/A'])[0],
        'form': 'Comprimé',
        'therapeutic_area': 'N/A',
        'status': 'commercialise'
    }

    # Process sites data - match each site with address and country
    sites = annotations_by_type.get('site', [])
    addresses = annotations_by_type.get('adresse', []) + annotations_by_type.get('address', [])
    countries = annotations_by_type.get('pays', []) + annotations_by_type.get('country', [])

    sites_data = []
    max_sites = max(len(sites), len(addresses), len(countries))

    for i in range(max_sites):
        site_name = sites[i] if i < len(sites) else f'Site {i + 1}'
        address = addresses[i] if i < len(addresses) else 'N/A'
        country = countries[i] if i < len(countries) else 'N/A'

        sites_data.append({
            'site_name': site_name,
            'country': country,
            'city': address,  # Using address as city for now
            'gmp_certified': False
        })

    print(f"DEBUG: Creating product '{product_data['name']}' with {len(sites_data)} sites")
    for site in sites_data:
        print(f"DEBUG: Site - {site['site_name']} in {site['country']}, {site['city']}")

    # Create product if we have minimum required info
    if product_data['name'] and product_data['name'] != 'Unknown Product':
        try:
            product = Product.objects.create(
                name=product_data['name'],
                active_ingredient=product_data['active_ingredient'],
                dosage=product_data['dosage'],
                form=product_data['form'],
                therapeutic_area=product_data['therapeutic_area'],
                status=product_data['status']
            )

            # Create manufacturing sites
            for site_data in sites_data:
                ManufacturingSite.objects.create(
                    product=product,
                    site_name=site_data['site_name'],
                    country=site_data['country'],
                    city=site_data['city'],
                    gmp_certified=site_data['gmp_certified']
                )
                print(f"DEBUG: Created site: {site_data['site_name']}")

            return product

        except Exception as e:
            print(f"Error creating product: {e}")
            return None

    return None


@expert_required
def validate_document(request, document_id):
    """Validate entire document and create product if it's a manufacturer document"""
    if request.method == 'POST':
        try:
            document = get_object_or_404(RawDocument, id=document_id)

            # Debug: Check document type
            print(f"DEBUG: Document type = '{document.doc_type}'")

            # Create product from annotations
            product = create_product_from_annotations(document)

            if product:
                messages.success(
                    request,
                    f'🎉 Document validé avec succès! Le produit "{product.name}" a été créé dans le module client.'
                )

                # Log the action
                log_expert_action(
                    user=request.user,
                    action='document_validated_product_created',
                    annotation=None,
                    document_id=document.id,
                    document_title=document.file.name,
                    reason=f"Document validated and product created: {product.name}"
                )

                return redirect('expert:document_list')
            else:
                # Get detailed debug info
                debug_info = debug_annotations_for_product(document)
                messages.warning(
                    request,
                    f'❌ Produit non créé. Détails: {debug_info}'
                )

            return redirect('expert:document_list')

        except Exception as e:
            messages.error(request, f'❌ Erreur lors de la validation: {str(e)}')
            return redirect('expert:review_document', document_id=document_id)

    return redirect('expert:review_document', document_id=document_id)


def debug_annotations_for_product(document):
    """Debug function to show what annotations are available"""
    validated_annotations = Annotation.objects.filter(
        page__document=document,
        validation_status__in=['validated', 'expert_created']
    )

    debug_info = []
    debug_info.append(f"Doc type: '{document.doc_type}'")
    debug_info.append(f"Total annotations: {validated_annotations.count()}")

    # Check what annotation types we have
    annotation_types = {}
    for annotation in validated_annotations:
        annotation_type = annotation.annotation_type.name.lower()
        if annotation_type not in annotation_types:
            annotation_types[annotation_type] = []
        annotation_types[annotation_type].append(annotation.selected_text)

    debug_info.append(f"Available types: {list(annotation_types.keys())}")

    # Check for required fields
    has_product = 'product' in annotation_types
    has_dosage = 'dosage' in annotation_types
    has_site = 'site' in annotation_types

    debug_info.append(f"Has product: {has_product}")
    debug_info.append(f"Has dosage: {has_dosage}")
    debug_info.append(f"Has site: {has_site}")

    return " | ".join(debug_info)