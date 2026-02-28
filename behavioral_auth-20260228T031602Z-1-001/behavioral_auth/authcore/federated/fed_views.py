from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from authcore.federated.model_store import get_registry, add_pending_update


class FederatedModelView(APIView):
    def get(self, request):
        registry = get_registry()
        return Response({
            'version': registry['current_version'],
            'message': 'Download global model from /authcore/ml/global_model.pkl',
        })


class FederatedUpdateView(APIView):
    def post(self, request):
        weights = request.data.get('weights', [])
        version = request.data.get('version', 1)
        user_id = request.data.get('user_id', 'anonymous')
        if not weights:
            return Response({'error': 'No weights provided'}, status=status.HTTP_400_BAD_REQUEST)
        success, msg = add_pending_update(weights, version, user_id)
        if not success:
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        registry = get_registry()
        return Response({'accepted': True, 'message': msg, 'current_version': registry['current_version']})


class FederatedStatusView(APIView):
    def get(self, request):
        registry = get_registry()
        return Response(registry)
    
    def head(self, request):
        return Response({})
