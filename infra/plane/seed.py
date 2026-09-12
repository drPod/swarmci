"""Executed inside the pinned Plane API container, using its own Django models."""
import json
import sys
import uuid
from importlib import import_module

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from plane.db.models import User, Profile, Workspace, WorkspaceMember, Project, ProjectMember, State, Issue
from plane.license.models import Instance

def operate(request):
    with transaction.atomic():
        if request['operation'] == 'create':
            suffix = uuid.uuid4().hex[:16]
            instance = Instance.objects.first()
            if instance is None:
                instance = Instance.objects.create(instance_name='Swarm test deployment', instance_id=str(uuid.uuid4()),
                    current_version='v1.2.3', last_checked_at=timezone.now(), is_test=True)
            instance.is_setup_done = True
            instance.is_telemetry_enabled = False
            instance.save()
            user = User.objects.create(username='swarm-'+suffix, email='swarm-'+suffix+'@example.test',
                first_name='Swarm', last_name='Explorer', display_name='Swarm Explorer', is_email_verified=True)
            user.set_unusable_password()
            user.save()
            workspace = Workspace.objects.create(name='Swarm Workspace', slug='swarm-'+suffix, owner=user)
            WorkspaceMember.objects.create(workspace=workspace, member=user, role=20)
            Profile.objects.update_or_create(user=user, defaults={'is_onboarded':True,'is_tour_completed':True,
                'last_workspace_id':workspace.id})
            project = Project.objects.create(workspace=workspace, name='Launch Mission', identifier='SWARM',
                project_lead=user, cycle_view=True, module_view=True, issue_views_view=True)
            ProjectMember.objects.create(workspace=workspace, project=project, member=user, role=20)
            states = []
            for index, (name, group, color) in enumerate([('Backlog','backlog','#60646c'),('Todo','unstarted','#60646c'),
                ('In Progress','started','#f59e0b'),('Done','completed','#16a34a'),('Cancelled','cancelled','#ef4444')]):
                states.append(State.objects.create(workspace=workspace, project=project, name=name, group=group,
                    color=color, sequence=index, default=index==0))
            project.default_state=states[0]
            project.save()
            aliases = {'workspace_slug':workspace.slug,'workspace':str(workspace.id),'user':str(user.id),
                'email':user.email,'project':str(project.id)}
            for state in states:
                aliases['state_'+state.group] = str(state.id)
            for index, name in enumerate(['Launch checklist','Design review','Ship release']):
                issue=Issue.objects.create(workspace=workspace, project=project, name=name, state=states[1],
                    description_html='<p>Swarm exploration: edit, filter, archive and restore this work item.</p>',
                    priority=['high','medium','low'][index], created_by=user, updated_by=user)
                aliases['issue_'+str(index+1)] = str(issue.id)
            session = import_module(settings.SESSION_ENGINE).SessionStore()
            session['_auth_user_id']=str(user.id)
            session['_auth_user_backend']='django.contrib.auth.backends.ModelBackend'
            session['_auth_user_hash']=user.get_session_auth_hash()
            session.save()
            result={'id':suffix,'aliases':aliases,'cookie':{'name':settings.SESSION_COOKIE_NAME,'value':session.session_key}}
        elif request['operation'] == 'snapshot':
            workspace=Workspace.objects.get(slug='swarm-'+request['id'])
            rows=Issue.all_objects.filter(workspace=workspace).order_by('sequence_id') if hasattr(Issue,'all_objects') else Issue.objects.filter(workspace=workspace).order_by('sequence_id')
            result={'issues':list(rows.values('id','name','sequence_id','state_id','priority','description_html','archived_at','deleted_at','parent_id'))}
            from plane.db import models as plane_models
            for model_name, fields in {
                'Cycle': ['id','name','description','start_date','end_date','owned_by_id','project_id'],
                'Module': ['id','name','description','status','project_id'],
                'Page': ['id','name','description_html','access','archived_at'],
                'IssueView': ['id','name','filters','display_filters','project_id'],
                'Label': ['id','name','color','project_id'],
                'IssueComment': ['id','issue_id','comment_html','access'],
                'CycleIssue': ['id','cycle_id','issue_id'],
                'ModuleIssue': ['id','module_id','issue_id'],
                'IssueLabel': ['id','label_id','issue_id'],
                'IssueAssignee': ['id','assignee_id','issue_id'],
                'IssueRelation': ['id','issue_id','related_issue_id','relation_type'],
            }.items():
                model=getattr(plane_models,model_name,None)
                if model is None: continue
                available={f.attname for f in model._meta.fields}
                if 'workspace_id' not in available: continue
                selected=[f for f in fields if f in available]
                result[model_name]=list(model.objects.filter(workspace=workspace).order_by('created_at','id').values(*selected))
        elif request['operation'] == 'delete':
            # Only this generated disposable identity; never reset a shared database.
            users=User.objects.filter(username='swarm-'+request['id'],email='swarm-'+request['id']+'@example.test')
            from plane.db.models import Session
            Session.objects.filter(user_id__in=[str(u) for u in users.values_list('id',flat=True)]).delete()
            users.delete()
            result={'deleted':True}
        else:
            raise ValueError('Unknown fixture operation')
    from plane.utils.cache import invalidate_cache_directly
    if request['operation'] != 'snapshot':
        invalidate_cache_directly('/api/instances/', user=False)
    return result
