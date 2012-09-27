from . import util, numpy, _

class AffineTransformation( object ):
  'affine transformation'

  def __init__( self, offset, transform ):
    'constructor'

    self.offset = numpy.asarray( offset )
    self.transform = numpy.asarray( transform )

  @util.cachefunc
  def eval( self, points ):
    'apply transformation'

    if self.transform.ndim == 0:
      coords = self.offset[:,_] + self.transform * points.coords
    elif self.transform.shape[1] == 0:
      assert points.coords.shape == (0,1)
      coords = self.offset[:,_]
    else:
      coords = self.offset[:,_] + numpy.dot( self.transform, points.coords )
    return LocalPoints( coords, points.weights )

class Element( object ):
  '''Element base class.

  Represents the topological shape.'''

  def eval( self, where ):
    'get points'

    if isinstance( where, str ):
      points = self.getischeme( self.ndims, where )
    else:
      where = numpy.asarray( where )
      points = LocalPoints( where )
    return points

  def zoom( self, elemset, points ):
    'zoom points'

    elem = self
    totaltransform = 1
    while elem not in elemset:
      elem, transform = self.parent
      points = transform( points )
      totaltransform = numpy.dot( transform.transform, totaltransform )
    return elem, points, totaltransform

class CustomElement( Element ):
  'custom element'

  def __init__( self, **ischemes ):
    'constructor'

    self.ischemes = ischemes

  def getischeme( self, ndims, where ):
    'get integration scheme'

    assert ndims == self.ndims
    return self.ischemes[ where ]

class QuadElement( Element ):
  'quadrilateral element'

  def __init__( self, ndims, parent=None ):
    'constructor'

    self.ndims = ndims
    self.parent = parent
    Element.__init__( self )

  @util.classcache
  def edgetransform( cls, ndims ):
    'edge transforms'

    transforms = []
    for idim in range( ndims ):
      for iside in range( 2 ):
        offset = numpy.zeros( ndims )
        offset[idim:] = 1-iside
        offset[:idim+1] = iside
        transform = numpy.zeros(( ndims, ndims-1 ))
        transform.flat[ :(ndims-1)*idim :ndims] = 1 - 2 * iside
        transform.flat[ndims*(idim+1)-1::ndims] = 2 * iside - 1
        transforms.append( AffineTransformation( offset=offset, transform=transform ) )
    return transforms

  def edge( self, iedge ):
    'edge'

    transform = self.edgetransform( self.ndims )[ iedge ]
    return QuadElement( self.ndims-1, parent=(self,transform) )

  @util.classcache
  def refinedtransform( cls, ndims, n ):
    'refined transform'

    transforms = []
    transform = 1. / n
    for i in range( n**ndims ):
      offset = numpy.zeros( ndims )
      for idim in range( ndims ):
        offset[ ndims-1-idim ] = transform * ( i % n )
        i //= n
      transforms.append( AffineTransformation( offset=offset, transform=transform ) )
    return transforms

  @util.cachefunc
  def refined( self, n ):
    'refine'

    return [ QuadElement( self.ndims, parent=(self,transform) ) for transform in self.refinedtransform( self.ndims, n ) ]

  @util.classcache
  def getischeme( cls, ndims, where ):
    'get integration scheme'

    if ndims == 0:
      return LocalPoints( numpy.zeros([0,1]), numpy.array([1.]) )

    x = w = None
    if where.startswith( 'gauss' ):
      N = int( where[5:] )
      k = numpy.arange( 1, N )
      d = k / numpy.sqrt( 4*k**2-1 )
      x, w = numpy.linalg.eigh( numpy.diagflat(d,-1) ) # eigh operates (by default) on lower triangle
      w = w[0]**2
      x = ( x + 1 ) * .5
    elif where.startswith( 'uniform' ):
      N = int( where[7:] )
      x = numpy.arange( .5, N ) / N
      w = util.appendaxes( 1./N, N )
    elif where.startswith( 'bezier' ):
      N = int( where[6:] )
      x = numpy.linspace( 0, 1, N )
      w = util.appendaxes( 1./N, N )
    elif where.startswith( 'subdivision' ):
      N = int( where[11:] ) + 1
      x = numpy.linspace( 0, 1, N )
      w = None
    elif where.startswith( 'contour' ):
      N = int( where[7:] )
      p = numpy.linspace( 0, 1, N )
      if ndims == 1:
        coords = p[_]
      elif ndims == 2:
        coords = numpy.array([ p[ range(N) + [N-1]*(N-2) + range(N)[::-1] + [0]*(N-2) ],
                               p[ [0]*(N-1) + range(N) + [N-1]*(N-2) + range(1,N)[::-1] ] ])
      elif ndims == 3:
        assert N == 0
        coords = numpy.array([ [0,0,0], [1,0,0], [0,1,0], [1,1,0], [0,0,1], [1,0,1], [0,1,1], [1,1,1] ]).T
      else:
        raise Exception, 'contour not supported for ndims=%d' % ndims
    else:
      raise Exception, 'invalid element evaluation %r' % where
    if x is not None:
      coords = reduce( lambda coords, i:
        numpy.concatenate(( x[:,_].repeat( N**i, 1 ).reshape( 1, -1 ),
                       coords[:,_].repeat( N,    1 ).reshape( i, -1 ) )), range( 1, ndims ), x[_] )
    if w is not None:
      weights = reduce( lambda weights, i: ( weights * w[:,_] ).ravel(), range( 1, ndims ), w )
    else:
      weights = None
    return LocalPoints( coords, weights )

  def __repr__( self ):
    'string representation'

    return '%s#%x<ndims=%d>' % ( self.__class__.__name__, id(self), self.ndims )

class TriangularElement( Element ):
  'triangular element'

  ndims = 2
  edgetransform = (
    AffineTransformation( offset=[0,0], transform=[[ 1],[ 0]] ),
    AffineTransformation( offset=[1,0], transform=[[-1],[ 1]] ),
    AffineTransformation( offset=[0,1], transform=[[ 0],[-1]] ) )

  def __init__( self, parent=None ):
    'constructor'

    self.parent = parent
    Element.__init__( self )

  def edge( self, iedge ):
    'edge'

    transform = self.edgetransform[ iedge ]
    return QuadElement( ndims=1, parent=(self,transform) )

  @util.classcache
  def refinedtransform( cls, n ):
    'refined transform'

    transforms = []
    scale = 1./n
    for i in range( n ):
      transforms.extend( AffineTransformation( offset=numpy.array( [i,j], dtype=float ) / n, transform=scale ) for j in range(0,n-i) )
      transforms.extend( AffineTransformation( offset=numpy.array( [n-j,n-i], dtype=float ) / n, transform=-scale ) for j in range(n-i,n) )
    return transforms

  def refined( self, n ):
    'refine'

    if n == 1:
      return self
    return [ TriangularElement( parent=(self,transform) ) for transform in self.refinedtransform( n ) ]

  @util.classcache
  def getischeme( cls, ndims, where ):
    '''get integration scheme
    gaussian quadrature: http://www.cs.rpi.edu/~flaherje/pdf/fea6.pdf
    '''

    assert ndims == 2
    if where.startswith( 'contour' ):
      n = int( where[7:] or 0 )
      p = numpy.arange( n+1, dtype=float ) / (n+1)
      z = numpy.zeros_like( p )
      coords = numpy.hstack(( [1-p,p], [z,1-p], [p,z] ))
      weights = None
    elif where == 'gauss1':
      coords = numpy.array( [[1],[1]] ) / 3.
      weights = numpy.array( [1] ) / 2.
    elif where in 'gauss2':
      coords = numpy.array( [[4,1,1],[1,4,1]] ) / 6.
      weights = numpy.array( [1,1,1] ) / 6.
    elif where == 'gauss3':
      coords = numpy.array( [[5,9,3,3],[5,3,9,3]] ) / 15.
      weights = numpy.array( [-27,25,25,25] ) / 96.
    elif where == 'gauss4':
      A = 0.091576213509771; B = 0.445948490915965; W = 0.109951743655322
      coords = numpy.array( [[1-2*A,A,A,1-2*B,B,B],[A,1-2*A,A,B,1-2*B,B]] )
      weights = numpy.array( [W,W,W,1/3.-W,1/3.-W,1/3.-W] ) / 2.
    elif where == 'gauss5':
      A = 0.101286507323456; B = 0.470142064105115; V = 0.125939180544827; W = 0.132394152788506
      coords = numpy.array( [[1./3,1-2*A,A,A,1-2*B,B,B],[1./3,A,1-2*A,A,B,1-2*B,B]] )
      weights = numpy.array( [1-3*V-3*W,V,V,V,W,W,W] ) / 2.
    elif where == 'gauss6':
      A = 0.063089014491502; B = 0.249286745170910; C = 0.310352451033785; D = 0.053145049844816; V = 0.050844906370207; W = 0.116786275726379
      VW = 1/6. - (V+W) / 2.
      coords = numpy.array( [[1-2*A,A,A,1-2*B,B,B,1-C-D,1-C-D,C,C,D,D],[A,1-2*A,A,B,1-2*B,B,C,D,1-C-D,D,1-C-D,C]] )
      weights = numpy.array( [V,V,V,W,W,W,VW,VW,VW,VW,VW,VW] ) / 2.
    elif where == 'gauss7':
      A = 0.260345966079038; B = 0.065130102902216; C = 0.312865496004875; D = 0.048690315425316; U = 0.175615257433204; V = 0.053347235608839; W = 0.077113760890257
      coords = numpy.array( [[1./3,1-2*A,A,A,1-2*B,B,B,1-C-D,1-C-D,C,C,D,D],[1./3,A,1-2*A,A,B,1-2*B,B,C,D,1-C-D,D,1-C-D,C]] )
      weights = numpy.array( [1-3*U-3*V-6*W,U,U,U,V,V,V,W,W,W,W,W,W] ) / 2.
    elif where[:7] == 'uniform' or where[:6] == 'bezier':
      if where[:7] == 'uniform':
        N = int( where[7:] )
        points = ( numpy.arange( N ) + 1./3 ) / N
      else:
        N = int( where[6:] )
        points = numpy.linspace( 0, 1, N )
      NN = N**2
      C = numpy.empty( [2,N,N] )
      C[0] = points[:,_]
      C[1] = points[_,:]
      coords = C.reshape( 2, NN )
      flip = coords[0] + coords[1] > 1
      coords[:,flip] = 1 - coords[::-1,flip]
      weights = util.appendaxes( .5/NN, NN )
    else:
      raise Exception, 'invalid element evaluation: %r' % where
    return LocalPoints( coords, weights )

  def __repr__( self ):
    'string representation'

    return '%s#%x' % ( self.__class__.__name__, id(self) )

class LocalPoints( object ):
  'local point coordinates'

  def __init__( self, coords, weights=None ):
    'constructor'

    self.coords = coords
    self.weights = weights
    self.ndims, self.npoints = coords.shape

  def __getitem__( self, item ):
    'get item'

    return LocalPoints( self.coords[item], self.weights )

class StdElem( object ):
  'stdelem base class'

  def __mul__( self, other ):
    'multiply elements'

    return PolyProduct( self, other )

class PolyProduct( StdElem ):
  'multiply standard elements'

  @util.classcache
  def __new__( cls, std1, std2 ):
    'constructor'

    self = object.__new__( cls )
    self.std1 = std1
    self.std2 = std2
    self.ndims = std1.ndims + std2.ndims
    return self

  @util.cachefunc
  def eval( self, points, grad=0 ):
    'evaluate'

    s1 = slice(0,self.std1.ndims)
    p1 = points[s1]
    s2 = slice(self.std1.ndims,None)
    p2 = points[s2]

    S = slice(None),
    N = numpy.newaxis,

    G12 = [ util.reshape( self.std1.eval( p1, grad=i )[S+S+N+S*i+N*j]
                        * self.std2.eval( p2, grad=j )[S+N+S+N*i+S*j], 1, 2 )
            for i,j in zip( range(grad,-1,-1), range(grad+1) ) ]

    data = numpy.empty( [ points.npoints, self.std1.nshapes * self.std2.nshapes ] + [ self.ndims ] * grad )

    s12 = numpy.array([s1,s2])
    R = numpy.arange(grad)
    for n in range(2**grad):
      index = n>>R&1
      data[S*2+tuple(s12[index])] = G12[index.sum()].transpose(0,1,*2+index.argsort())

    return data

  def __str__( self ):
    'string representation'

    return '%s*%s' % ( self.std1, self.std2 )

class PolyLine( StdElem ):
  'polynomial on a line'

  @classmethod
  def bernstein_poly( cls, degree ):
    'bernstein polynomial coefficients'

    # magic bernstein triangle
    n = degree - 1
    poly = numpy.zeros( [n+1,n+1], dtype=int )
    root = (-1)**n
    for k in range(n//2+1):
      poly[k,k] = root
      for i in range(k+1,n+1-k):
        root = poly[i,k] = poly[k,i] = ( root * (k+i-n-1) ) / i
      root = ( poly[k,k+1] * (k*2-n+1) ) / (k+1)
    return poly

  @classmethod
  def spline_poly( cls, p, n ):
    'spline polynomial coefficients'

    assert n < 2*(p-1)
    extractions = numpy.empty(( n, p, p ))
    extractions[0] = numpy.eye( p )
    for i in range( 1, n ):
      extractions[i] = numpy.eye( p )
      for j in range( 2, p ):
        for k in reversed( range( j, p ) ):
          alpha = 1. / min( 2+k-j, n-i+1 )
          extractions[i-1,:,k] = alpha * extractions[i-1,:,k] + (1-alpha) * extractions[i-1,:,k-1]
        extractions[i,-j-1:-1,-j-1] = extractions[i-1,-j:,-1]

    poly = cls.bernstein_poly( p )
    return util.contract( extractions[:,_,:,:], poly[_,:,_,:], axis=-1 )

  @util.classcache
  def spline_elems( cls, p, n ):
    'spline elements, minimum amount (just for caching)'

    return map( cls, cls.spline_poly(p,n) )

  @util.classcache
  def spline_elems_neumann( cls, p, n ):
    'spline elements, neumann endings (just for caching)'

    polys = cls.spline_poly(p,n)
    poly_0 = polys[0].copy()
    poly_0[:,1] += poly_0[:,0]
    poly_e = polys[-1].copy()
    poly_e[:,-2] += poly_e[:,-1]
    return cls(poly_0), cls(poly_e)

  @classmethod
  def spline( cls, degree, nelems, periodic=False, neumann=0 ):
    'spline elements, any amount'

    p = degree
    n = 2*(p-1)-1
    if periodic:
      assert not neumann, 'periodic domains have no boundary'
      elems = cls.spline_elems( p, n )[p-2:p-1] * nelems
    else:
      elems = cls.spline_elems( p, min(nelems,n) )
      if len(elems) < nelems:
        elems = elems[:p-2] + elems[p-2:p-1] * (nelems-2*(p-2)) + elems[p-1:]
      if neumann:
        elem_0, elem_e = cls.spline_elems_neumann( p, min(nelems,n) )
        if neumann & 1:
          elems[0] = elem_0
        if neumann & 2:
          elems[-1] = elem_e
        
    return numpy.array( elems )

  def __init__( self, poly ):
    'constructor'

    self.ndims = 1
    self.poly = numpy.asarray( poly, dtype=float )
    self.degree, self.nshapes = self.poly.shape

  @util.cachefunc
  def eval( self, points, grad=0 ):
    'evaluate'

    if grad >= self.degree:
      return util.appendaxes( 0., (points.npoints,self.nshapes)+(1,)*grad )

    poly = self.poly
    for n in range(grad):
      poly = poly[:-1] * numpy.arange( poly.shape[0]-1, 0, -1 )[:,_]

    x, = points.coords
    polyval = poly[0,_,:].repeat( x.size, axis=0 )
    for p in poly[1:]:
      polyval *= x[:,_]
      polyval += p[_,:]

    return polyval[(Ellipsis,)+(_,)*grad]

  def __repr__( self ):
    'string representation'

    return 'PolyLine#%x' % id(self)

class PolyTriangle( StdElem ):
  'poly triangle'

  @util.classcache
  def __new__( cls, order ):
    'constructor'

    assert order == 1
    self = object.__new__( cls )
    return self

  @util.cachefunc
  def eval( self, points, grad=0 ):
    'eval'

    if grad == 0:
      x, y = points.coords
      data = numpy.array( [ x, y, 1-x-y ] ).T
    elif grad == 1:
      data = numpy.array( [[[1,0],[0,1],[-1,-1]]], dtype=float )
    else:
      data = numpy.array( 0 ).reshape( (1,) * (grad+1+points.ndim) )
    return data

  def __repr__( self ):
    'string representation'

    return '%s#%x' % ( self.__class__.__name__, id(self) )

class ExtractionWrapper( object ):
  'extraction wrapper'

  def __init__( self, stdelem, extraction ):
    'constructor'

    self.stdelem = stdelem
    self.extraction = extraction

  @util.cachefunc
  def eval( self, points, grad=0 ):
    'call'

    return util.transform( self.stdelem.eval( points, grad ), self.extraction.T, axis=1 )

  def __repr__( self ):
    'string representation'

    return '%s#%x:%s' % ( self.__class__.__name__, id(self), self.stdelem )

# vim:shiftwidth=2:foldmethod=indent:foldnestmax=2
