"""
Tests for branding page
"""


import datetime

import six
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponseRedirect
from django.test.client import RequestFactory
from django.test.utils import override_settings
from django.urls import reverse
from milestones.tests.utils import MilestonesTestCaseMixin
from mock import Mock, patch
from pytz import UTC

from lms.djangoapps.branding.views import index
from lms.djangoapps.courseware.tests.helpers import LoginEnrollmentTestCase
from common.djangoapps.edxmako.shortcuts import render_to_response
from openedx.core.djangoapps.site_configuration.tests.mixins import SiteMixin
from util.milestones_helpers import set_prerequisite_courses
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory

FEATURES_WITH_STARTDATE = settings.FEATURES.copy()
FEATURES_WITH_STARTDATE['DISABLE_START_DATES'] = False
FEATURES_WO_STARTDATE = settings.FEATURES.copy()
FEATURES_WO_STARTDATE['DISABLE_START_DATES'] = True


def mock_render_to_response(*args, **kwargs):
    """
    Mock the render_to_response function
    """
    return render_to_response(*args, **kwargs)

RENDER_MOCK = Mock(side_effect=mock_render_to_response)


class AnonymousIndexPageTest(ModuleStoreTestCase):
    """
    Tests that anonymous users can access the '/' page,  Need courses with start date
    """
    def setUp(self):
        super(AnonymousIndexPageTest, self).setUp()
        self.factory = RequestFactory()
        self.course = CourseFactory.create(
            days_early_for_beta=5,
            enrollment_start=datetime.datetime.now(UTC) + datetime.timedelta(days=3),
            user_id=self.user.id,
        )

    @override_settings(FEATURES=FEATURES_WITH_STARTDATE)
    def test_none_user_index_access_with_startdate_fails(self):
        """
        This is a regression test for a bug where the incoming user is
        anonymous and start dates are being checked.  It replaces a previous
        test as it solves the issue in a different way
        """
        self.client.logout()
        response = self.client.get(reverse('root'))
        self.assertEqual(response.status_code, 200)

    @override_settings(FEATURES=FEATURES_WITH_STARTDATE)
    def test_anon_user_with_startdate_index(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    @override_settings(FEATURES=FEATURES_WO_STARTDATE)
    def test_anon_user_no_startdate_index(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    @override_settings(X_FRAME_OPTIONS='ALLOW')
    def test_allow_x_frame_options(self):
        """
        Check the x-frame-option response header
        """

        # check to see that the override value is honored
        resp = self.client.get('/')
        self.assertEqual(resp['X-Frame-Options'], 'ALLOW')

    def test_deny_x_frame_options(self):
        """
        Check the x-frame-option response header
        """

        # check to see that the default setting is to DENY iframing
        resp = self.client.get('/')
        self.assertEqual(resp['X-Frame-Options'], 'DENY')

    def test_edge_redirect_to_login(self):
        """
        Test edge homepage redirect to lms login.
        """

        request = self.factory.get('/')
        request.user = AnonymousUser()

        # HTTP Host changed to edge.
        request.META["HTTP_HOST"] = "edge.edx.org"
        response = index(request)

        # Response should be instance of HttpResponseRedirect.
        self.assertIsInstance(response, HttpResponseRedirect)
        # Location should be "/login".
        self.assertEqual(response._headers.get("location")[1], "/login")  # pylint: disable=protected-access


class PreRequisiteCourseCatalog(ModuleStoreTestCase, LoginEnrollmentTestCase, MilestonesTestCaseMixin):
    """
    Test to simulate and verify fix for disappearing courses in
    course catalog when using pre-requisite courses
    """
    ENABLED_SIGNALS = ['course_published']

    @patch.dict(settings.FEATURES, {'ENABLE_PREREQUISITE_COURSES': True})
    def test_course_with_prereq(self):
        """
        Simulate having a course which has closed enrollments that has
        a pre-req course
        """
        pre_requisite_course = CourseFactory.create(
            org='edX',
            course='900',
            display_name='pre requisite course',
            emit_signals=True,
        )

        pre_requisite_courses = [six.text_type(pre_requisite_course.id)]

        # for this failure to occur, the enrollment window needs to be in the past
        course = CourseFactory.create(
            org='edX',
            course='1000',
            display_name='course that has pre requisite',
            # closed enrollment
            enrollment_start=datetime.datetime(2013, 1, 1),
            enrollment_end=datetime.datetime(2014, 1, 1),
            start=datetime.datetime(2013, 1, 1),
            end=datetime.datetime(2030, 1, 1),
            pre_requisite_courses=pre_requisite_courses,
            emit_signals=True,
        )
        set_prerequisite_courses(course.id, pre_requisite_courses)

        resp = self.client.get('/')

        # make sure both courses are visible in the catalog
        self.assertContains(resp, 'pre requisite course')
        self.assertContains(resp, 'course that has pre requisite')


class IndexPageCourseCardsSortingTests(ModuleStoreTestCase):
    """
    Test for Index page course cards sorting
    """
    ENABLED_SIGNALS = ['course_published']

    def setUp(self):
        super(IndexPageCourseCardsSortingTests, self).setUp()
        self.starting_later = CourseFactory.create(
            org='MITx',
            number='1000',
            display_name='Starting later, Announced later',
            metadata={
                'start': datetime.datetime.now(UTC) + datetime.timedelta(days=4),
                'announcement': datetime.datetime.now(UTC) + datetime.timedelta(days=3),
            },
            emit_signals=True,
        )
        self.starting_earlier = CourseFactory.create(
            org='MITx',
            number='1001',
            display_name='Starting earlier, Announced earlier',
            metadata={
                'start': datetime.datetime.now(UTC) + datetime.timedelta(days=2),
                'announcement': datetime.datetime.now(UTC) + datetime.timedelta(days=1),
            },
            emit_signals=True,
        )
        self.course_with_default_start_date = CourseFactory.create(
            org='MITx',
            number='1002',
            display_name='Tech Beta Course',
            emit_signals=True,
        )
        self.factory = RequestFactory()

    @patch('common.djangoapps.student.views.management.render_to_response', RENDER_MOCK)
    @patch('lms.djangoapps.courseware.views.views.render_to_response', RENDER_MOCK)
    @patch.dict('django.conf.settings.FEATURES', {'ENABLE_COURSE_DISCOVERY': False})
    def test_course_discovery_off(self):
        """
        Asserts that the Course Discovery UI elements follow the
        feature flag settings
        """
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        # assert that the course discovery UI is not present
        self.assertNotContains(response, 'Search for a course')

        # check the /courses view
        response = self.client.get(reverse('courses'))
        self.assertEqual(response.status_code, 200)

        # assert that the course discovery UI is not present
        self.assertNotContains(response, 'Search for a course')
        self.assertNotContains(response, '<aside aria-label="Refine Your Search" class="search-facets phone-menu">')

        # make sure we have the special css class on the section
        self.assertContains(response, '<div class="courses no-course-discovery"')

    @patch('common.djangoapps.student.views.management.render_to_response', RENDER_MOCK)
    @patch('lms.djangoapps.courseware.views.views.render_to_response', RENDER_MOCK)
    @patch.dict('django.conf.settings.FEATURES', {'ENABLE_COURSE_DISCOVERY': True})
    def test_course_discovery_on(self):
        """
        Asserts that the Course Discovery UI elements follow the
        feature flag settings
        """
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        # assert that the course discovery UI is not present
        self.assertContains(response, 'Search for a course')

        # check the /courses view
        response = self.client.get(reverse('courses'))
        self.assertEqual(response.status_code, 200)

        # assert that the course discovery UI is present
        self.assertContains(response, 'Search for a course')
        self.assertContains(response, '<aside aria-label="Refine Your Search" class="search-facets phone-menu">')
        self.assertContains(response, '<div class="courses"')

    @patch('common.djangoapps.student.views.management.render_to_response', RENDER_MOCK)
    @patch('lms.djangoapps.courseware.views.views.render_to_response', RENDER_MOCK)
    @patch.dict('django.conf.settings.FEATURES', {'ENABLE_COURSE_DISCOVERY': False})
    def test_course_cards_sorted_by_default_sorting(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        ((template, context), _) = RENDER_MOCK.call_args  # pylint: disable=unpacking-non-sequence
        self.assertEqual(template, 'index.html')

        # by default the courses will be sorted by their creation dates, earliest first.
        self.assertEqual(context['courses'][0].id, self.starting_earlier.id)
        self.assertEqual(context['courses'][1].id, self.starting_later.id)
        self.assertEqual(context['courses'][2].id, self.course_with_default_start_date.id)

        # check the /courses view
        response = self.client.get(reverse('courses'))
        self.assertEqual(response.status_code, 200)
        ((template, context), _) = RENDER_MOCK.call_args  # pylint: disable=unpacking-non-sequence
        self.assertEqual(template, 'courseware/courses.html')

        # by default the courses will be sorted by their creation dates, earliest first.
        self.assertEqual(context['courses'][0].id, self.starting_earlier.id)
        self.assertEqual(context['courses'][1].id, self.starting_later.id)
        self.assertEqual(context['courses'][2].id, self.course_with_default_start_date.id)

    @patch('common.djangoapps.student.views.management.render_to_response', RENDER_MOCK)
    @patch('lms.djangoapps.courseware.views.views.render_to_response', RENDER_MOCK)
    @patch.dict('django.conf.settings.FEATURES', {'ENABLE_COURSE_SORTING_BY_START_DATE': False})
    @patch.dict('django.conf.settings.FEATURES', {'ENABLE_COURSE_DISCOVERY': False})
    def test_course_cards_sorted_by_start_date_disabled(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        ((template, context), _) = RENDER_MOCK.call_args  # pylint: disable=unpacking-non-sequence
        self.assertEqual(template, 'index.html')

        # now the courses will be sorted by their announcement dates.
        self.assertEqual(context['courses'][0].id, self.starting_later.id)
        self.assertEqual(context['courses'][1].id, self.starting_earlier.id)
        self.assertEqual(context['courses'][2].id, self.course_with_default_start_date.id)

        # check the /courses view as well
        response = self.client.get(reverse('courses'))
        self.assertEqual(response.status_code, 200)
        ((template, context), _) = RENDER_MOCK.call_args  # pylint: disable=unpacking-non-sequence
        self.assertEqual(template, 'courseware/courses.html')

        # now the courses will be sorted by their announcement dates.
        self.assertEqual(context['courses'][0].id, self.starting_later.id)
        self.assertEqual(context['courses'][1].id, self.starting_earlier.id)
        self.assertEqual(context['courses'][2].id, self.course_with_default_start_date.id)


class IndexPageProgramsTests(SiteMixin, ModuleStoreTestCase):
    """
    Tests for Programs List in Marketing Pages.
    """
    def test_get_programs_with_type_called(self):
        views = [
            (reverse('root'), 'common.djangoapps.student.views.management.get_programs_with_type'),
            (reverse('courses'), 'lms.djangoapps.courseware.views.views.get_programs_with_type'),
        ]
        for url, dotted_path in views:
            with patch(dotted_path) as mock_get_programs_with_type:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                mock_get_programs_with_type.assert_called_once()
