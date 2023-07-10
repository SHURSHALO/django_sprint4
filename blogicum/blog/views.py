from django.utils import timezone
from blog.models import Post, Category, Comment
from django.views.generic import (
    CreateView,
    UpdateView,
    DetailView,
)
from blog.forms import PostForm, CommentForm, ProfileForm, PasswordChangeForm
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import get_user_model
from django.http import Http404


User = get_user_model()


def profile_view(request, username):
    current_time = timezone.now()
    user = get_object_or_404(User, username=username)
    edit_profile_url = reverse_lazy(
        'blog:edit_profile', kwargs={'username': user.username}
    )
    if request.user.username == username:
        posts = (
            Post.objects.filter(author__username=username)
            .annotate(comment_count=Count('comment'))
            .order_by('-pub_date')
        )

    else:
        posts = (
            Post.objects.filter(
                author__username=username,
                is_published=True,
                category__is_published=True,
                pub_date__lte=current_time,
            )
            .annotate(comment_count=Count('comment'))
            .order_by('-pub_date')
        )

    paginator = Paginator(posts, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'profile': user,
        'edit_profile_url': edit_profile_url,
        'page_obj': page_obj,
    }
    return render(request, 'blog/profile.html', context)


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileForm
    template_name = 'blog/user.html'

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse_lazy(
            'blog:profile', kwargs={'username': self.request.user.username}
        )


@login_required
def password_change_view(request, username):
    user = request.user
    if request.method == 'POST':
        form = PasswordChangeForm(user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            return redirect('blog:password_change_done')
    else:
        form = PasswordChangeForm(user)
    context = {'form': form}
    return render(request, 'blog/password_change_form.html', context)


def post(request, pk=None):
    post = get_object_or_404(
        Post,
        pub_date__lte=timezone.now(),
        is_published=True,
        category__is_published=True,
        id=pk,
    )
    if pk is not None:
        instance = get_object_or_404(Post, pk=pk)
    else:
        instance = None
    form = PostForm(files=request.FILES or None, instance=instance)
    if form.is_valid():
        form.save()
    context = {'form': form, 'post': post}
    return render(request, 'blog/create.html', context)


class PostMixin:
    model = Post
    form_class = PostForm
    template_name = 'blog/create.html'


class PostCreateView(LoginRequiredMixin, PostMixin, CreateView):
    pk_url_kwarg = 'post_id'

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)


class PostUpdateView(LoginRequiredMixin, PostMixin, UpdateView):
    pk_url_kwarg = 'post_id'

    def dispatch(self, request, *args, **kwargs):
        if self.get_object().author != self.request.user:
            return redirect('blog:post_detail', self.kwargs['post_id'])
        return super().dispatch(request, *args, **kwargs)


@login_required
def delete_post(request, post_id):
    template_name = 'blog/create.html'
    delete_post = get_object_or_404(
        Post, pk=post_id, author__username=request.user
    )
    if request.method != "POST":
        context = {
            'post': delete_post,
        }
        return render(request, template_name, context)
    delete_post.delete()
    return redirect('blog:profile', request.user)


class PostDetailView(DetailView):
    model = Post
    template_name = 'blog/detail.html'
    context_object_name = 'post'
    pk_url_kwarg = 'post_id'

    def get_object(self):
        object = super(PostDetailView, self).get_object()
        if self.request.user != object.author and (
            not object.is_published or not object.category.is_published
        ):
            raise Http404()
        return object

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = CommentForm()
        context['comments'] = self.object.comment.select_related('author')
        return context


def index(request):
    template = 'blog/index.html'
    current_time = timezone.now()
    post = (
        Post.objects.select_related('category')
        .filter(
            pub_date__lte=current_time,
            is_published=True,
            category__is_published=True,
        )
        .annotate(comment_count=Count('comment'))
        .order_by('-pub_date')
    )
    paginator = Paginator(post, 10)

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {'page_obj': page_obj}
    return render(request, template, context)


def category_posts(request, category_slug):
    template = 'blog/category.html'
    current_time = timezone.now()
    category = get_object_or_404(
        Category, slug=category_slug, is_published=True
    )
    post_list = (
        Post.objects.select_related('category')
        .filter(
            category__slug=category_slug,
            is_published=True,
            pub_date__lte=current_time,
        )
        .order_by('-pub_date')
    )
    paginator = Paginator(post_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {'category': category, 'page_obj': page_obj}
    return render(request, template, context)


@login_required
def add_comment(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    form = CommentForm(request.POST)

    if form.is_valid():
        comment = form.save(commit=False)
        comment.author = request.user
        comment.post = post
        comment.save()
    return redirect('blog:post_detail', post_id)


@login_required
def edit_comment(request, post_id, comment_id):
    comment = get_object_or_404(
        Comment, id=comment_id, author__username=request.user
    )

    if request.method == 'POST':
        form = CommentForm(request.POST, instance=comment)
        if form.is_valid():
            form.save()
            return redirect('blog:post_detail', post_id)
    else:
        form = CommentForm(instance=comment)
    contex = {'form': form, 'comment': comment}

    return render(request, 'blog/comment.html', contex)


@login_required
def delete_comment(request, post_id, comment_id):
    template = 'blog/comment.html'
    comment = get_object_or_404(Comment, id=comment_id)
    if comment.author == request.user and request.method == "POST":
        comment.delete()
        return redirect('blog:post_detail', post_id)
    contex = {'comment': comment}
    return render(request, template, contex)